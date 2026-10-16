# Roteiro de teste pessoal — Felipe

## Prontidão e ambiente

A PR90 (branch feat/video-project-engines, head d4b04a8) NÃO tem implantação comprovada por esta frente. Os quatro fluxos novos e VSL motion abaixo só podem ser testados após disponibilizar frontend + backend + worker compatíveis da PR90 em ambiente controlado. Não procurar esses controles na produção antiga. Rollout será coordenado separadamente; este guia não o executa nem o autoriza.

Código conferido: rota `/media`, aba **Gravações**. Conta precisa de acesso à empresa e permissão de mídia. Se a rota for negada, pedir acesso ao responsável; não alterar permissões para contornar. Selecionar a empresa correta no perfil. Usar projetos NOVOS de teste; não abrir campanha21 ou rascunhos encerrados.

Na base anterior a310ae1, a tela chama **Gravações**, botão **Nova gravação**. Permite roteiro, upload, ordenação e trechos manuais; não tem o compositor novo. Na PR90, chama **Gravações e projetos**, botão **Novo projeto de vídeo** e seção **Projeto de vídeo · combinar formatos e cenas**. Esses nomes são um diagnóstico da versão, não confirmação de implantação. Não há servidor local completo deixado em execução. A página temporária usada na prova do formulário já foi encerrada.

## O que pode ser conferido na versão anterior

1. Em `/media` → **Gravações**, **Nova gravação** → preencher **Título** e **Roteiro** → **Salvar roteiro**.
2. Em **Brutos · vídeos, fotos e áudios**, **Adicionar ou retomar arquivos**. Usar somente vídeos/fotos/áudios próprios ou autorizados. Esperar todos ficarem **Recebido**; enviar não começa edição.
3. **Conferir original**; selecionar arquivos, usar **↑ Subir / ↓ Descer** e **Trechos mantidos**. Exemplo próprio: manter0–5s e10–15s de um vídeo de20s. **Adicionar trecho mantido** remove o intervalo intermediário, não escolhe automaticamente uma ideia com sentido.
4. Somente se o responsável confirmar worker compatível e janela de teste, **Tudo enviado — começar edição** gera uma prévia real. Conferir em **Prévia e feedback** → **Versão**. Essa ação consome recursos; não clicar para testar mera presença da tela.
5. Este teste valida montagem/trim legado. Não prova nenhum dos quatro modos novos ou seleção automática.

## Preparação comum para PR90 em ambiente controlado

O responsável deve fornecer a URL exata do ambiente e confirmar os três componentes compatíveis; não basta servir o frontend. O worker deve anunciar recording_batch:v1, recording_edits:v2 e recording_project:v1. Não orientar Felipe a executar comandos de infraestrutura.

1. Abrir a URL fornecida + `/media` → **Gravações** → **Novo projeto de vídeo**.
2. Preencher **Título** (`TESTE — nome do fluxo`) e **Roteiro** → **Salvar roteiro**. Não importar Reel histórico.
3. Se o fluxo usa materiais, enviá-los em **Adicionar ou retomar arquivos**, esperar **Recebido**, marcar **Incluir … na edição** e conferir originais.
4. Expandir **Projeto de vídeo · combinar formatos e cenas**. Usar esse compositor, não o botão legado **Tudo enviado — começar edição**.
5. Preencher **Roteiro completo desta versão de vídeo**, **Referência de marca aprovada (fonte@versão)** e cores confirmadas. `fixture/original@1` serve apenas para demonstração técnica, nunca como aprovação da marca Britto.
6. Selecionar entradas, formato e áudio. **Silêncio intencional** só quando esse é o resultado desejado; para voz enviada, selecionar **Narração/áudio enviado** e o arquivo. Não há geração automática de voz.
7. Conferir títulos, texto, duração e intervalo de cada cena. **Distribuir roteiro em rascunho de cenas** faz divisão mecânica por frases, não criação editorial. Legendas usam **Adicionar legenda**, início/fim/texto; não exigem JSON.
8. Conferir materiais/licenças, ordem e duração total. Só então **Tudo enviado e cenas definidas — gerar prévia do projeto**. Fecha uma versão e enfileira render; não publica.

## Casos mínimos separados

| Caso | Material mínimo e ações no compositor PR90 | Resultado objetivo a verificar |
|---|---|---|
| Longo → cortes | Vídeo próprio com fala; idealmente2–5min para primeiro teste, com um trecho de15–30s previamente escolhido e transcrito por pessoa. Marcar **Cortes de vídeo longo**; visual **Trecho de vídeo enviado**; escolher material, início e duração. Preencher por que funciona sozinho, trecho completo da transcrição e referência. Informar direitos. | Corte começa/termina no ponto escolhido, preserva uma ideia completa e áudio sincronizado. A escolha foi humana fornecida; não registrar como seleção semântica automática. STT Groq e proposta via OpenCode existentes não foram validados por esta fatia. |
| Enriquecer brutos | Vídeo próprio de10–20s e imagem própria opcional. Marcar **Edição enriquecida**; cena footage com enquadramento/cor; adicionar cena **Texto / gráfico em motion**, dado+fonte se gráfico; imagem/meme autorizado opcional com autorização separada; **Adicionar legenda**. | Corte/enquadramento sem cortar rosto relevante; título só sobrepor se desejado; texto e captions legíveis, sem duplicar texto queimado; overlay no intervalo correto; dado conferível; fala intacta. Não é NLE completo. |
| Faceless | Roteiro curto original de3–5frases, sem vídeo. Marcar **Faceless sem footage**; cenas motion ou imagens autorizadas. Pode usar silêncio explícito ou áudio próprio enviado. | Render sem upload de footage, cenas na ordem, texto integral sem sumiço, duração coerente. Não há busca/geração automática de B-roll/imagem/narração nem roteiro criativo automático. |
| Stickman | Roteiro original curto; nenhum asset obrigatório. Marcar **Bonecos palito**; pelo menos uma cena **Boneco palito original**; escolher ação explicar/acenar/mover; título/texto e duração. | Boneco aparece, braço não gira fora do ombro, ação e cenas respeitam o tempo, captions sem cobrir conteúdo importante. Motor procedural básico; não promessa de animação narrativa sofisticada. |
| VSL / mini-VSL motion | Roteiro próprio com abertura, argumento, prova e fechamento; sem footage. Marcar **VSL / mini-VSL de motion**, formato **Horizontal16:9 · VSL longa**, cenas motion/stickman/imagens autorizadas e voz própria opcional. Começar30–60s; longo só em janela separada. | Ordem e duração completas, texto legível, fontes das provas presentes, voz não truncada, início/meio/fim reproduzíveis. Dez minutos ainda NÃO têm render comprovado: ensaio preparado600s/18.000frames/160×90, bloqueado por CPU/swap. Não afirmar desempenho720p/1080p ou VSL comercial aprovada. |

Após cada caso funcionar sozinho, criar outro projeto misto selecionando duas ou mais entradas e alternando cenas. Selecionar modo exige cena correspondente; não marcar todos só para passar no teste.

## Provas a guardar por tentativa

- URL/ambiente, versão de software informada pelo responsável, data, empresa e conta criadora; captura da tela com título do teste.
- ID da gravação, prévia vN, jobID/status, roteiro e parâmetros usados, nomes/origens/autorização dos materiais.
- MP4 daquela versão, duração/resolução/FPS/hash fornecidos pelo backend/worker, captura inicial/intermediária/final e lista de defeitos com tempo exato. Não inferir sucesso do simples estado queued ou do upload concluído.
- Assistir e ouvir o vídeo inteiro; pausar nos cortes/transições; anotar sincronismo, legibilidade, enquadramento, identidade, ritmo e direitos. Se não ouviu/viu, marcar NOT_TESTED.
- **Salvar feedback na vN** guarda feedback; não o aplica automaticamente. Para corrigir, **Adicionar mais brutos / nova edição**, ajustar e gerar nova versão. Histórico deve continuar acessível; uma aprovação anterior não pode aprovar a nova versão.

## Revisão e ponto de parada obrigatório deste teste

Na PR90, outra conta humana autorizada, diferente da criadora, abre **Revisão criativa da prévia renderizada** → **Abrir roteiro e evidências desta versão**. Ler os conteúdos locais AntiSlop/Taste, preencher aplicação concreta, sete critérios, frames/trechos realmente conferidos e achados. **Salvar revisão e achados desta versão** não aprova nem agenda. Não inventar uma segunda identidade nem preencher PASS sem observação. FAIL/NOT_TESTED e P0/P1 abertos impedem elegibilidade.

Depois de revisão elegível, **Conferência humana desta prévia** exige áudio, captions, rosto/enquadramento, safe zones e direitos → **Registrar conferência do arquivo**. Registrar somente após checar de verdade. Para teste negativo, usar outro projeto: **Motivo da reprovação** → **Reprovar esta prévia**; a versão deve continuar preservada e bloqueada para aprovação.

PARAR antes de **Aprovar vídeo, copies e calendário** e **Agendar e distribuir nos canais aprovados**. O teste pessoal não autoriza destinos/copy/horário ou postagem real. Não há publicação comprovada por esta entrega. Publicação exige autorização específica do conteúdo e destino, revisão final da versão exata e rollout separado pelo integrador; nenhum deploy, build pesado, geração paga ou postagem foi feito para produzir este guia.
