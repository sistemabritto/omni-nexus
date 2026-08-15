# LEARNINGS.md — EvoNexus

Aprendizados duráveis de sessões. Formato: data — contexto → lição.

## 2026-08-15

- **Shares Nexus não são apontados por diretório, e sim por caminho fixo no banco.** O token em `file_shares` (SQLite) guarda `path`; `/api/shares/<token>/view` serve sempre aquele arquivo. Trocar o conteúdo de um link exige `UPDATE file_shares SET path=... WHERE token=...`. Copiar arquivo para `workspace/shares/` não muda o que o link serve — o caminho no banco vence.
- **Investigar o sistema antes de assumir cache.** "Continua mostrando 105" não era cache do navegador nem do Nexus — era o token apontando para o arquivo antigo. Consultar `file_shares` no SQLite resolveu a causa raiz em uma query.
- **Relatório de 304 reels do @caiomktviral**: pipeline coleta (feed/user + max_id) → Groq Whisper (288 transcritos) → Britto-Vision/OmniRoute. Dados em `workspace/reach-caiomktviral-100/`. HTML gerado: `workspace/reports/[C]analise-304-reels-caiomktviral.html`.