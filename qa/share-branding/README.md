# Branding de visualização compartilhada

Incremento separado após UI SHA `7db75035e40e4cc72f3460ceb45ee0a0f5141d41`. Branch `codex/share-branding`. Não modifica commit de UI em rollout, backend, produção ou arquivos antigos.

## Escopo verificado

`dashboard/frontend/src/pages/ShareView.tsx` possui visualização pública HTML (iframe sandbox), Markdown, código, texto, imagem, vídeo, áudio e PDF; todos usam um rodapé comum. Foi adicionado logo Sistema Britto clicável para https://sistemabritto.com.br, ao lado da atribuição EvoNexus preexistente, incluindo aviso e copyright Evolution Foundation. O viewer reserva espaço para o rodapé, inclusive safe-area. Sem pixel/analytics externos.

Logo usado sem redesenhar: `/home/sistemabritto/Documentos/sistemabritto-site/public/images/logo-sistema-britto.png`, o mesmo referenciado por `components/Navbar.tsx`. Copiado para `dashboard/frontend/public/branding/sistema-britto.png` com proporção original. SVG horizontal alternativo contém placeholder base64 incompleto, por isso não foi utilizado.

Share/export são distintos: o rodapé pertence ao viewer `/share/:token`. Downloads/streams originais e conteúdos dentro do iframe não recebem injeção. Nenhum artefato existente é regravado ou republicado. Embutir marca em PDF/imagem/vídeo, exportações DOCX/PPTX ou HTML baixado requer definição dos geradores e eventual contrato backend; não foi implementado por inferência. Os downloads existentes seguem originais. Nenhum compartilhamento externo foi criado.

## Validação

Build TypeScript/Vite e `git diff --check`. `qa.cjs` intercepta somente endpoints share e não cria shares; testa os oito tipos de visualização e link expirado em 375 e 1440px. Valida logo carregado, backlink exato, foco de teclado, alvo >=44px, crédito/logo upstream, copyright, espaço reservado e ausência de overflow. Arquivos binários do QA são vazios: os testes confirmam a moldura/branding, não reprodução de mídia ou conteúdo PDF. As limitações preexistentes de blob/CSP em preview de imagem/PDF não são corrigidas neste incremento, pois exigem coordenação de contrato/configuração. Capturas HTML/Markdown são fixtures locais explicitamente identificadas.

Resultado: build passou; 18 casos de viewer passaram (9 estados × 2 larguras), logo carregado, backlink/foco corretos, créditos preservados, sem overflow e rodapé dentro da área reservada. Capturas revisadas. ESLint isolado encontra um erro preexistente em `ShareView` no `setState` síncrono para token ausente, já presente antes deste incremento; não se alterou essa lógica ou suprimiram regras. `lint.log` registra a ocorrência. O aviso Vite de chunk preexistente >500kB permanece.
