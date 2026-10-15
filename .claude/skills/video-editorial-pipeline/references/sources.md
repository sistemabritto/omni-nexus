# Proveniência das ideias

Síntese original baseada na análise fornecida pelo coordenador, sem baixar ou
incorporar código/mídia dos projetos e sem alegar leitura direta do PDF.

- [get-brolls — engenheirodevideo](https://github.com/engenheirodevideo/get-brolls):
  segundo análise recebida, CLI Python/JSON com busca, storyboard/prévias,
  aprovação e coleta. Aproveitamos a separação planejar→revisar→coletar. Código
  MIT não concede direitos da mídia retornada; storyboard sem autenticação não
  deve ser exposto publicamente. Nenhuma instalação ou integração automática.
- [awesome-opus5-5-videos — yihui-dev](https://github.com/yihui-dev/awesome-opus5-5-videos):
  catálogo de exemplos/prompts e referências de HTML/Canvas/SVG/Three.js.
  Aproveitamos o vocabulário visual; não tratamos como engine, nem copiamos
  clipes ou prompts extensos.
- SeeCut: análise recebida indica licença Noncommercial. Não incorporamos código,
  dependências ou assets; nenhuma integração proposta enquanto essa análise
  estiver incompleta.
- *Let Claude Edit Your Videos*, TheCreatorStack, @pauloshimas2026, 13 páginas.
  PDF identificado pelo coordenador como Library
  `libfile_a3046aa8a50c81918b3a2ff79756685a`; não materializado nem lido nesta
  execução. Atribuição à síntese fornecida: p.5 transcrição por palavra,
  glossário e frames; p.7 beat sheet aprovado; pp.7–8 rough cut antes de efeitos
  e cortes sem dividir palavras; p.8 sincronia, safe zones, rosto e áudio;
  p.10 similaridade de estilo sem cópia; p.12 prévia, snapshots, feedback por
  timestamp e preservação da versão anterior. Não reproduzimos texto/imagens
  do PDF e não universalizamos seus exemplos numéricos de pausa ou zoom.

O mapa fonte→editado e o validador temporal são implementação própria para
manter essas decisões coerentes depois de cortes. Nenhuma fonte substitui a
aprovação do Felipe ou a verificação dos direitos de cada asset.

- [motion-skills — iart-ai](https://github.com/iart-ai/motion-skills), hub MIT com
  packs separados, conforme análise recebida. Padrões úteis de
  [tiktok-video-skills](https://github.com/iart-ai/tiktok-video-skills): caption-animation
  e short-form-video; de [b-roll-skills](https://github.com/iart-ai/b-roll-skills):
  talking-head-b-roll, composição HTML/canvas/FFmpeg e QA de overlap,
  transparência, facebox e transições. Aplicamos só essas decisões ao contrato,
  sem instalar packs/scripts. Facebox é configuração, não tracking; o limite
  de 80 quadros pede amostragem. B-roll não substitui rough cut/reframe/escala
  nem legendagem completa. Seleção de transcrição exige inspeção: a análise
  encontrou prioridade ElevenLabs quando a chave existe, apesar do texto da
  skill; usar local explicitamente quando autorizado, sem confiar nos defaults.
  Remotion tem licença própria, separada do MIT de exemplos. Nenhum código,
  prompt extenso ou mídia desses packs foi incorporado.
