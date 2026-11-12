# Origem e modificações

Origem: https://github.com/Jakeschincariol/instagram-agent-skill, commit `d03c56bb598be770c60b201f94237e5d1a4268a6`. MIT integral em LICENSE; Copyright (c) 2026 Jake Schincariol. Adaptado pelo OmniNexus em 2026-10-15: recorte PT-BR editorial para Pixel/coprodutor, sem plugin completo, scripts, renderizador, publicação ou MCP.

Lidos antes de adaptar neste pin: LICENSE, README.md, skills/ig-reel/SKILL.md, skills/ig-caption/SKILL.md, skills/ig-repurpose/SKILL.md, skills/ig-human/SKILL.md e skills/ig-viral/SKILL.md. Fonte fixada: https://github.com/Jakeschincariol/instagram-agent-skill/tree/d03c56bb598be770c60b201f94237e5d1a4268a6/skills .

Preservado: três opções de gancho, roteiro, texto visual/beat sheet, legenda/CTA e extração de unidades do bruto. Modificado: respeitar o JSON único do coprodutor e protocolos locais, sem outputs/chaves extras, sem caminho global de voz/log, sem fórmulas rígidas ou garantias de duração/cadência.

Scripts não incorporados ou executados. Contagem/pontuação/CTA centrados em inglês/ASCII não validam PT-BR; parsers de números abreviados/baseline de auditoria exigiriam revisão própria. Não usamos score de viralidade/humanidade, promessa de detecção, remoção automática de Unicode ou metas universais. AUC0,56 é relato do autor sobre seu corpus no README, não resultado reproduzido aqui nem prova de previsão de vencedor.

Vínculos: `.claude/agents/pixel-social-media.md`, `.claude/agents/reels-copilot.md`, `.claude/skills/social-reels-scripts/SKILL.md`. O handler real `dashboard/backend/reels_copilot.py` usa `agent=""` e por isso não recebe a persona: a orientação local é incluída explicitamente no prompt existente, sem mudar schema/handlers/produção/Postiz. Ausência do arquivo registra aviso e preserva protocolo anterior.

Testes conferem descoberta/loader e prompt efetivamente passado a uma chamada mockada que retorna falha antes de qualquer gravação. Não gera roteiro real, não roda heartbeat/tick nem chama CRM/OpenReply/Postiz. Contratos e revisão humana de asset/hash/copy/canais/calendário permanecem exigências do fluxo vigente, não nova API implementada neste lote.
