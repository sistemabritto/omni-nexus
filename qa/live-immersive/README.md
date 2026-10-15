# Live — superfície de voz original

Refinamento visual independente do link Live entregue em `2132224` / PR46. Não atrasa sua integração. Layout mobile-first em tela ampla, foco visual central, indicador de microfone, ação principal grande, encerrar acessível e transcrição recolhível. Paleta/typografia Sistema Britto, CSS e composição originais; nenhum código, imagem ou asset Mark-LV/MegaBrain foi usado. UI/UX Pro Max aplicada a hierarquia, foco, alvos e redução de movimento.

Os handlers de estado/áudio/sessão foram comparados byte a byte com a base e permanecem iguais. Apenas a apresentação deriva desligado/conectando/ouvindo/respondendo dos estados já existentes. Não há chamada automática, reconexão automática, chave, flag ou API nova. A página continua identificada como prévia e sem ferramentas de produção. Bloqueios retornados pelo fluxo existente permanecem visíveis; não se mostra uma sessão ativa fictícia.

Corrige também o metadado do cabeçalho: `/live` era identificado como Conversa central por ausência de entrada no mapa de apresentação. Agora mostra Live nos três locales. Não altera autorização ou registro da rota.

## Evidência

TypeScript/Vite e ESLint do componente passaram; após o metadado, Vite foi repetido. Aviso preexistente de chunk >500kB permanece. QA Chrome local em 375×667, 812×375 e 1440×900 com todas as APIs/WebSockets interceptados e captura de mic substituída por bloqueio de teste. Verifica título, layout sem overflow horizontal, teclado/foco da transcrição, estado inicial desligado, bloqueio de configuração após clique, ação de tentar novamente e zero chamadas ao microfone no mount ou tentativa bloqueada. Capturas idle/blocked e results.json nesta pasta.

Não é validação Gemini, conversa de áudio real ou sessão autenticada em produção. Estados ouvindo/respondendo usam o fluxo existente e não foram exercitados com áudio real nesta rodada. Safari, leitor de tela e dispositivo físico não testados. Sem implantação por esta tarefa e sem novo gate de revisão visual; integrador segue o fluxo existente.
