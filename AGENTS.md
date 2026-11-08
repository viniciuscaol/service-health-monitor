# Colaboração

- Trabalhar em branch própria, registrar a demanda em issue e entregar uma PR vinculada.
- Não fazer push direto na main nem merge sem solicitação explícita do proprietário.
- Executar pytest e node --check monitor/static/app.js antes da PR.
- Manter os testes independentes de serviços externos e usar apenas dados fictícios em exemplos.
- Não adicionar credenciais, URLs internas reais ou bancos SQLite ao versionamento.
- Manter o projeto pequeno: HTTP, TCP, TLS, SQLite e painel local. Novas integrações são demandas separadas.
- Descrever o que foi efetivamente testado; não apresentar este laboratório como serviço de produção.
