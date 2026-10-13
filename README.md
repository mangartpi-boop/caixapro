# CaixaPro — controle de caixa empresarial (versão 1)

Aplicativo web responsivo, com autenticação, cadastro de clientes, entradas e saídas, filtros por mês/cliente/tipo, relatórios, exportação CSV (abre no Excel) e impressão em PDF. Os dados ficam em SQLite no servidor.

## Rodar no Windows

1. Instale **Python 3.10 ou superior** em https://www.python.org/downloads/ (marque *Add Python to PATH*).
2. Extraia o ZIP e abra o terminal na pasta `caixa_empresa_web`.
3. Antes do primeiro uso, defina uma senha de administrador de pelo menos 12 caracteres:

   **PowerShell:** `$env:ADMIN_PASSWORD="SuaSenhaForteAqui123!"`

   **Prompt de Comando (CMD):** `set ADMIN_PASSWORD=SuaSenhaForteAqui123!`

4. Execute: `python server.py`
5. Abra http://127.0.0.1:8000 e entre com usuário **admin** e a senha escolhida.

A senha é necessária para a primeira criação do banco. O arquivo `caixa.db` é criado automaticamente e mantém os registros após reiniciar.

## Publicação na internet

O pacote é um **projeto executável, não um serviço hospedado**. Para acesso pela internet, implante em um servidor com armazenamento persistente, HTTPS obrigatório e proxy reverso (Nginx/Caddy). Defina `HOST=127.0.0.1` atrás do proxy, `COOKIE_SECURE=1`, `ADMIN_PASSWORD` e um caminho persistente em `CAIXA_DB`. Configure backups automáticos e acesso restrito ao servidor.

**Importante:** a versão 1 é um MVP para validação. Antes de operar com dados empresariais reais na internet, acrescente proteção contra tentativas repetidas de login, sessões persistentes com expiração/revogação, recuperação de senha, logs de auditoria, permissões por usuário, proteção e política de backup, testes de segurança e revisão LGPD. O armazenamento de sessões atual é em memória e é perdido ao reiniciar. O usuário administrador inicial é único.

## Observações

- Valores financeiros são armazenados em centavos (inteiros).
- O saldo exibido é a diferença entre entradas e saídas do período filtrado; não inclui saldo inicial nem conciliação bancária.
- Exportação em CSV com separador `;`, compatível com Excel brasileiro.
- O PDF pode ser salvo pelo botão **Imprimir / Salvar PDF** do navegador.
- O arquivo `caixa.db` contém dados sensíveis: não o publique em repositórios ou envie a terceiros.
