import os,json,sqlite3,hashlib,hmac,secrets,datetime,csv,io,threading
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from urllib.parse import urlparse,parse_qs
from http import cookies
from pathlib import Path
ROOT=Path(__file__).resolve().parent
DB=Path(os.environ.get('CAIXA_DB',str(ROOT/'caixa.db')))
HOST=os.environ.get('HOST','127.0.0.1');PORT=int(os.environ.get('PORT','8000'))
LOCK=threading.Lock(); SESSIONS={}
def conn():
 c=sqlite3.connect(DB,timeout=15);c.row_factory=sqlite3.Row;c.execute('PRAGMA foreign_keys=ON');return c
def setup():
 with conn() as c:
  c.executescript('''CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,username TEXT UNIQUE NOT NULL,passhash TEXT NOT NULL,salt TEXT NOT NULL);CREATE TABLE IF NOT EXISTS clients(id INTEGER PRIMARY KEY,name TEXT NOT NULL,document TEXT DEFAULT '',phone TEXT DEFAULT '',email TEXT DEFAULT '',created_at TEXT DEFAULT CURRENT_TIMESTAMP);CREATE TABLE IF NOT EXISTS movements(id INTEGER PRIMARY KEY,kind TEXT NOT NULL CHECK(kind IN ('entrada','saida')),amount INTEGER NOT NULL CHECK(amount>0),date TEXT NOT NULL,description TEXT NOT NULL,category TEXT DEFAULT '',client_id INTEGER REFERENCES clients(id) ON DELETE SET NULL,payment TEXT DEFAULT '',created_at TEXT DEFAULT CURRENT_TIMESTAMP);CREATE INDEX IF NOT EXISTS ix_mov_date ON movements(date);CREATE INDEX IF NOT EXISTS ix_mov_client ON movements(client_id);''')
  if not c.execute('SELECT 1 FROM users LIMIT 1').fetchone():
   username=os.environ.get('ADMIN_USER','admin');password=os.environ.get('ADMIN_PASSWORD','')
   if not password: raise RuntimeError('Defina ADMIN_PASSWORD antes da primeira inicialização (mínimo 12 caracteres).')
   if len(password)<12:raise RuntimeError('ADMIN_PASSWORD precisa ter pelo menos 12 caracteres.')
   salt=secrets.token_hex(16);ph=hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),310000).hex()
   c.execute('INSERT INTO users(username,passhash,salt) VALUES(?,?,?)',(username,ph,salt))
def filters(q):
 wh=[];p=[]
 if q.get('month',[''])[0]:
  m=q['month'][0]
  if len(m)!=7 or m[4]!='-' or not m[:4].isdigit() or not m[5:].isdigit() or not 1<=int(m[5:])<=12:raise ValueError('Mês inválido')
  wh.append('substr(m.date,1,7)=?');p.append(m)
 if q.get('client_id',[''])[0]:wh.append('m.client_id=?');p.append(int(q['client_id'][0]))
 if q.get('kind',[''])[0]:wh.append('m.kind=?');p.append(q['kind'][0])
 return (' WHERE '+' AND '.join(wh)) if wh else '',p
def movrows(c,q):
 wh,p=filters(q)
 return [dict(x) for x in c.execute('SELECT m.*,cl.name client_name FROM movements m LEFT JOIN clients cl ON cl.id=m.client_id'+wh+' ORDER BY m.date DESC,m.id DESC',p)]
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*a):pass
 def respond(self,code,data,ctype='application/json',headers=None):
  body=json.dumps(data,ensure_ascii=False).encode() if ctype=='application/json' else data
  self.send_response(code);self.send_header('Content-Type',ctype+'; charset=utf-8');self.send_header('Content-Length',str(len(body)));self.send_header('X-Content-Type-Options','nosniff');self.send_header('X-Frame-Options','DENY');self.send_header('Referrer-Policy','no-referrer');self.send_header('Cache-Control','no-store')
  if headers:
   for k,v in headers.items():self.send_header(k,v)
  self.end_headers();self.wfile.write(body)
 def body(self):
  n=int(self.headers.get('Content-Length','0'))
  if n>100000:raise ValueError('Requisição muito grande')
  return json.loads(self.rfile.read(n) or b'{}')
 def session(self):
  jar=cookies.SimpleCookie()
  try:jar.load(self.headers.get('Cookie',''))
  except:pass
  token=jar.get('caixa_session');key=token.value if token else ''
  with LOCK:
   s=SESSIONS.get(key)
   if s and s[1]>datetime.datetime.now().timestamp():return s[0],key
  return None,key
 def do_GET(self):self.handle_request('GET')
 def do_POST(self):self.handle_request('POST')
 def do_PUT(self):self.handle_request('PUT')
 def do_DELETE(self):self.handle_request('DELETE')
 def handle_request(self,method):
  u=urlparse(self.path);path=u.path;q=parse_qs(u.query)
  try:
   if path=='/' and method=='GET':return self.respond(200,(ROOT/'static/index.html').read_bytes(),'text/html')
   if path=='/app.js' and method=='GET':return self.respond(200,(ROOT/'static/app.js').read_bytes(),'text/javascript')
   if path=='/style.css' and method=='GET':return self.respond(200,(ROOT/'static/style.css').read_bytes(),'text/css')
   if path=='/api/login' and method=='POST':
    d=self.body();user=str(d.get('username',''));pwd=str(d.get('password',''))
    with conn() as c:r=c.execute('SELECT * FROM users WHERE username=?',(user,)).fetchone()
    if not r or not hmac.compare_digest(hashlib.pbkdf2_hmac('sha256',pwd.encode(),bytes.fromhex(r['salt']),310000).hex(),r['passhash']):return self.respond(401,{'error':'Usuário ou senha incorretos'})
    token=secrets.token_urlsafe(40)
    with LOCK:SESSIONS[token]=(r['id'],datetime.datetime.now().timestamp()+8*3600)
    secure='; Secure' if os.environ.get('COOKIE_SECURE','0')=='1' else ''
    return self.respond(200,{'ok':True},headers={'Set-Cookie':'caixa_session='+token+'; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800'+secure})
   uid,token=self.session()
   if not uid:return self.respond(401,{'error':'Sessão expirada. Faça login.'})
   if method!='GET' and self.headers.get('Origin'):
    origin=self.headers['Origin'];host=self.headers.get('Host','')
    if not origin.endswith('://'+host):return self.respond(403,{'error':'Origem não permitida'})
   if path=='/api/logout' and method=='POST':
    with LOCK:SESSIONS.pop(token,None)
    return self.respond(200,{'ok':True},headers={'Set-Cookie':'caixa_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0'})
   if path=='/api/me' and method=='GET':return self.respond(200,{'ok':True})
   with conn() as c:
    if path=='/api/clients':
     if method=='GET':return self.respond(200,[dict(x) for x in c.execute('SELECT * FROM clients ORDER BY name')])
     if method=='POST':
      d=self.body();name=str(d.get('name','')).strip()
      if not name:raise ValueError('Nome obrigatório')
      cur=c.execute('INSERT INTO clients(name,document,phone,email) VALUES(?,?,?,?)',(name,str(d.get('document','')),str(d.get('phone','')),str(d.get('email',''))));c.commit();return self.respond(201,{'id':cur.lastrowid})
    if path.startswith('/api/clients/') and method in ('PUT','DELETE'):
     id=int(path.split('/')[-1])
     if method=='DELETE':c.execute('DELETE FROM clients WHERE id=?',(id,))
     else:
      d=self.body();name=str(d.get('name','')).strip()
      if not name:raise ValueError('Nome obrigatório')
      c.execute('UPDATE clients SET name=?,document=?,phone=?,email=? WHERE id=?',(name,str(d.get('document','')),str(d.get('phone','')),str(d.get('email','')),id))
     c.commit();return self.respond(200,{'ok':True})
    if path=='/api/movements':
     if method=='GET':return self.respond(200,movrows(c,q))
     if method=='POST':
      d=self.body();self.validate_mov(d);cur=c.execute('INSERT INTO movements(kind,amount,date,description,category,client_id,payment) VALUES(?,?,?,?,?,?,?)',self.movparams(d));c.commit();return self.respond(201,{'id':cur.lastrowid})
    if path.startswith('/api/movements/') and method in ('PUT','DELETE'):
     id=int(path.split('/')[-1])
     if method=='DELETE':c.execute('DELETE FROM movements WHERE id=?',(id,))
     else:
      d=self.body();self.validate_mov(d);c.execute('UPDATE movements SET kind=?,amount=?,date=?,description=?,category=?,client_id=?,payment=? WHERE id=?',(*self.movparams(d),id))
     c.commit();return self.respond(200,{'ok':True})
    if path=='/api/report' and method=='GET':
     rows=movrows(c,q);income=sum(r['amount'] for r in rows if r['kind']=='entrada');expense=sum(r['amount'] for r in rows if r['kind']=='saida')
     return self.respond(200,{'income':income,'expense':expense,'balance':income-expense,'count':len(rows),'by_category':[dict(x) for x in c.execute('SELECT kind,category,SUM(amount) total FROM movements GROUP BY kind,category ORDER BY total DESC')]})
    if path=='/api/export' and method=='GET':
     output=io.StringIO();w=csv.writer(output,delimiter=';');w.writerow(['Data','Tipo','Descrição','Categoria','Cliente','Pagamento','Valor (R$)'])
     for r in movrows(c,q):w.writerow([r['date'],r['kind'],r['description'],r['category'],r['client_name'] or '',r['payment'],f"{r['amount']/100:.2f}".replace('.',',')])
     return self.respond(200,b'\xef\xbb\xbf'+output.getvalue().encode('utf-8'),'text/csv',{'Content-Disposition':'attachment; filename="relatorio_caixa.csv"'})
   return self.respond(404,{'error':'Não encontrado'})
  except (ValueError,KeyError,sqlite3.IntegrityError,json.JSONDecodeError) as e:return self.respond(400,{'error':str(e)})
  except Exception as e:
   print('Server error:',repr(e));return self.respond(500,{'error':'Erro interno'})
 def validate_mov(self,d):
  if d.get('kind') not in ('entrada','saida'):raise ValueError('Tipo inválido')
  if not isinstance(d.get('amount'),int) or d['amount']<=0:raise ValueError('Valor inválido')
  datetime.date.fromisoformat(str(d.get('date','')))
  if not str(d.get('description','')).strip():raise ValueError('Descrição obrigatória')
 def movparams(self,d):return (d['kind'],d['amount'],d['date'],str(d['description']).strip(),str(d.get('category','')),int(d['client_id']) if d.get('client_id') else None,str(d.get('payment','')))
if __name__=='__main__':
 setup();print(f'Caixa web em http://{HOST}:{PORT}');ThreadingHTTPServer((HOST,PORT),Handler).serve_forever()
