# Changelog

Mudanças do Painel do Hotspot. Formato [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/), versões [SemVer](https://semver.org/lang/pt-BR/).

## [1.1.0] - 2026-10-06

### Adicionado
- Usuários: filtro por turma (tirada do comentário "Nome - Turma"), ações em lote (ativar, desativar, mudar perfil), "Nova senha" com um clique e impressão do cartão, coluna de senha e exportação para Excel com ou sem senhas.
- Conectados: botões para liberar (bypass) ou bloquear o aparelho com o MAC já preenchido.
- Perfis e horário: velocidade, aparelhos por usuário e tempo de sessão de cada perfil; horário de acesso por perfil com regras de firewall.
- Sites bloqueados pelo DNS do MikroTik (NXDOMAIN, com o site e subdomínios), com pausa e motivo.
- Consumo por usuário e por turma, com "Zerar contadores".
- Aviso da escola gravado em `aviso.txt` na pasta do hotspot, mostrado nas telas de login e de conectado.
- Histórico das ações com busca e filtros.
- Backup automático diário (últimas 30 cópias), backup na hora, download e restauração (só recria o que falta).

### Alterado
- A janela de confirmação responde ao clique nos botões, sem depender do evento de fechamento do navegador.

## [1.0.0] - 2026-10-06

### Adicionado
- Usuários, conectados, aparelhos (bypass e bloqueio), importação por planilha e impressão de credenciais.
- Instalação automática no Windows (`instalar.bat`), REST API do RouterOS 7 com HTTPS ou HTTP escolhido sozinho e `mikrotik-https.rsc` para ativar o www-ssl.
