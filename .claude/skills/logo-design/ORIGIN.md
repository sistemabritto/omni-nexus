# Origem, licença e auditoria

- Origem: https://github.com/kaankiziltug/logo-design-skill
- Commit fixado: `0ecf52e9a4b3ac92b714f7cc6e3148ab8c774134` (consultado em 2026-10-15).
- Adaptação textual OmniNexus: conhecimento para Canvas, sem instalação upstream.
- Fontes lidas antes de adaptar: `skills/logo-design/SKILL.md`, `references/discovery-brief.md`, `references/testing-checklist.md`, `templates/brand-guidelines-template.md`, `LICENSE`, `TRADEMARKS.md` e `references/library-guide.md` nesse commit.
- LICENSE e TRADEMARKS.md preservados integralmente ao lado deste arquivo. Código, documentação e templates upstream são MIT; os 1.432 SVGs de marcas são expressamente EXCLUÍDOS da MIT. Links fixados para repertório visual externo preservados em `references/visual-study.md`, sem download em massa. Nenhum SVG, biblioteca, galeria, catálogo, imagem de exemplo ou script foi incorporado.
- Referências locais são sínteses compatíveis com modo textual, não cópias que exigem ferramentas ausentes. Não há promessa de comandos de renderização ou exports instalados.

## Scripts — auditoria estática, sem execução

Leitura de `scripts/render_png.py`, `scripts/export_variants.py` e `scripts/svg_audit.py` no commit fixado. Nenhuma dependência instalada e nenhum código upstream executado.

- `render_png.py` encaminha SVG a backends externos sem sanitização de SVG; não é fronteira de confiança para arquivo não confiável.
- `export_variants.py` interpola título em XML sem escape e grava saídas que podem sobrescrever arquivos. Uma habilitação futura exigiria escape/validação, confinamento de caminhos e política contra sobrescrita.
- `svg_audit.py` mantém exit code 0 para resultados FAIL/WARN; rc só muda em exceção. Gate futuro deve consumir JSON e rejeitar explicitamente findings/política, não confiar em exit code ou score heurístico.

Esses scripts permanecem indisponíveis/desabilitados. Qualquer futura habilitação precisa de revisão específica; esta integração não a autoriza.

## Integração e limites

Descoberta pelo registro existente: `dashboard/backend/routes/skills.py` lista `.claude/skills/*/SKILL.md`. Vínculo: `.claude/agents/canvas-designer.md`. Sem mudança no mecanismo de execução, identidade, Live ou VoiceDream. `config/workspace.yaml` não está versionado nesta base: respeitar configuração efetiva quando disponível, sem criar dados de empresa.
