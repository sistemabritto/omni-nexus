# Catálogo de referências — escolher uma contribuição, não instalar um stack

Revisão documental: 15/10/2026. Links abaixo fixam as revisões consultadas;
licença de código, serviço, modelo, fonte, música e imagem são verificações
separadas. Nenhum projeto deste catálogo foi instalado ou executado. Este
catálogo complementa o contrato temporal e o release do PR56; não altera seus
endpoints nem substitui os gates humanos. Não duplica a estratégia editorial
específica de Reels mantida pelo executor de conhecimento.

## Decidir pelo problema

| Necessidade do plano aprovado | Referência útil | Critério de uso no OmniNexus |
|---|---|---|
| Faceless com roteiro, mídia, voz e legenda | MoneyPrinterTurbo | Estudar as fronteiras entre etapas e falhas; continuar no runtime atual, sem instalar outro pipeline. |
| Movimento de captions e composições curtas | motion-skills + packs iart | Escolher um padrão de hierarquia/entrada que melhore compreensão; manter palavras/tempos do contrato, sem refazer o corte. |
| Storyboard, B-roll e coleta | get-brolls | Apresentar storyboard/prévia antes da coleta autorizada; guardar origem/direitos. Não expor storyboard sem autenticação. |
| Demonstração/cena de produto | video-shotcraft | Descrever intenção do plano (enquadramento, movimento, luz, papel do produto), sem copiar o pacote; não aplicar receitas de produto automaticamente a bruto pessoal. |
| Renderizar a composição | HyperFrames **ou** Remotion | Manter HyperFrames já pinado como padrão. Remotion só em decisão explícita de arquitetura/licença; nunca iniciar dois motores por omissão. |
| Autocrop/extração de shorts | OpenShorts / Anil | Apenas referência de decomposição e QA até revisar licenças/dependências e provar a continuidade dos timestamps. |
| Outras esteiras completas | SeeCut / Hypit / OpenMontage | Conceitos gerais sob as restrições abaixo; nenhuma incorporação, serviço paralelo ou promessa de estabilidade. |

## Gates que o sucesso upstream não substitui

**Legendas:** não promover uma saída a pronta por `success`, `COMPLETE`, exit 0
ou pela existência de MP4. Exigir pacote de palavras com início/fim, glossário,
legendas sincronizadas na timeline editada e inspeção da versão embutida no
render (safe zones, rosto e legibilidade). Um upstream que desabilite legendas,
retorne caminho vazio, cues vazios ou pule etapa não cumpriu este gate. Para
brief sem fala, registrar o caso no beat sheet e voltar à revisão humana da
solução de texto/legendas; não dispensar o gate silenciosamente. Um plano v1
pode existir antes da transcrição; isso não torna o vídeo final aprovado.

**Proveniência:** exigir inventário de cada foto, B-roll, meme, música, fonte e
voz. Registrar origem (URL ou evidência de captura própria), titular/autor,
licença/consentimento aplicável, escopo de uso nos canais aprovados, atribuição,
data/restrições e hash do arquivo congelado. `rights_evidence` do contrato é uma
declaração a conferir, não prova automática. Arquivo incluído num repositório
MIT não ganha licença de mídia por associação. Ausência de evidência volta ao
plano para remover/substituir material, antes de render final e aprovação.

**Tempo:** adotar o `time_map` fonte→editado do PR56 para os intervalos keep da
revisão. Validar uma fala antes e outra depois de cada corte, a primeira/última
palavra e um trecho tardio de vídeo longo. Se transcrição vier em chunks, exigir
o offset original explícito; não concatenar tempos que reiniciam em zero, somar
o mesmo offset duas vezes ou ligar um efeito a uma palavra removida. Novos
cortes/re-enquadramentos que mudem a montagem exigem novo mapa/captions e QA.
A suspeita recebida sobre Anil **não é um defeito reproduzido nesta revisão**.

**Release:** rough cut → efeitos aprovados → prévia/snapshots/QA → revisão final
do Felipe. Legendas corrigidas ou material trocado exigem render novo, hash novo
e aprovação da revisão atual. Copy, contas/settings e calendário também integram
o digest; nada de reaproveitar aprovação antiga. Distribuir exclusivamente pelo
release/Postiz do OmniNexus com checkpoints por canal; resultado incerto exige
reconciliação. Não usar Upload-Post, publicadores embutidos ou contas externas.

## MoneyPrinterTurbo: contribuição limitada e verificável

Fonte fixada pelo pedido: [4b7b9657647bdb149715354269eec7e4dbad4a7a](https://github.com/harry0703/MoneyPrinterTurbo/tree/4b7b9657647bdb149715354269eec7e4dbad4a7a).
Código [MIT](https://github.com/harry0703/MoneyPrinterTurbo/blob/4b7b9657647bdb149715354269eec7e4dbad4a7a/LICENSE).

É uma implementação de pipeline, não só um catálogo de prompts. A contribuição
é separar roteiro/mídia/áudio/legendas/render e avaliar o resultado de cada etapa.
Em [task.py](https://github.com/harry0703/MoneyPrinterTurbo/blob/4b7b9657647bdb149715354269eec7e4dbad4a7a/app/services/task.py),
a geração de legendas pode ser desativada ou retornar vazio; há também caminho
de cross-post. Não importar esses defaults nem chamar `upload_post`: o caminho
de publicação continua sendo o release humano/Postiz existente.

A [lista de vozes](https://github.com/harry0703/MoneyPrinterTurbo/blob/4b7b9657647bdb149715354269eec7e4dbad4a7a/docs/voice-list.txt)
inclui pt-BR (Antonio, Francisca e Thalita). Isso ajuda a definir requisitos de
pronúncia/glossário, não concede acesso ao serviço, consentimento de voz ou
autorização para gerar áudio pago/enviar bruto privado. Escolha engine e destino
do áudio explicitamente; não inferir autorização da presença de API key.

Há arquivos em [resource/fonts](https://github.com/harry0703/MoneyPrinterTurbo/tree/4b7b9657647bdb149715354269eec7e4dbad4a7a/resource/fonts)
e [resource/songs](https://github.com/harry0703/MoneyPrinterTurbo/tree/4b7b9657647bdb149715354269eec7e4dbad4a7a/resource/songs).
Os direitos de cada um **não foram demonstrados nesta revisão**. Não copiar nem
usar esses arquivos como biblioteca autorizada; selecionar alternativas com
proveniência documentada. Nenhum runtime, dependência ou mídia foi trazido para
o projeto a partir dessa fonte.

## Registro de fontes e licenças — código não é uma permissão universal

| Fonte/revisão consultada | Licença/escopo conferido | Decisão para esta esteira |
|---|---|---|
| [motion-skills bb5a3ce](https://github.com/iart-ai/motion-skills/blob/bb5a3ce666110855a3437de2f70e9968c408e005/LICENSE) | MIT no hub. | Consultar padrões; conferir o pack usado separadamente. |
| [tiktok-video-skills 2a77533](https://github.com/iart-ai/tiktok-video-skills/blob/2a775336b5a638cbf8a61dbd785f9a1b649be016/LICENSE) | MIT. | caption-animation/short-form-video como vocabulário visual; sem copiar clipes/prompts extensos. |
| [b-roll-skills 2c7e555](https://github.com/iart-ai/b-roll-skills/blob/2c7e5550501098f1fff8d6d5651546cfd336824a/LICENSE) | MIT. | talking-head-b-roll depois do rough cut; facebox configurada, não tracking; QA overlap/alpha/transições; amostrar até 80 frames. Não executar transcribe.mjs por defaults. |
| [get-brolls 74d7e1c](https://github.com/engenheirodevideo/get-brolls/blob/74d7e1c49106e78accd20b28f908be3acb4c32f5/LICENSE) | MIT de código. | Storyboard→aprovação→coleta; direitos de resultados exigem verificação independente. |
| [video-shotcraft 13c74a7](https://github.com/Vincentwei1021/video-shotcraft/blob/13c74a707786872a18e3317e48c5c94011027620/LICENSE) | Apache License 2.0. | Referência de cenas de produto; mídia, áudio e runtime Remotion precisam análise própria. |
| [HyperFrames 76222e4](https://github.com/heygen-com/hyperframes/blob/76222e41d7760f94426484ceb9f76d0007813fcc/LICENSE) | Apache License 2.0; metadata do pacote local hyperframes 0.7.64 também declara Apache-2.0. | Motor já pinado no repo; manter sem instalar/upgradear neste lote. |
| [Remotion d6284c8](https://github.com/remotion-dev/remotion/blob/d6284c8161a36a33c850f7ee1b5354ca732db0d3/LICENSE.md) | **Remotion License**, com Free License / Company License conforme elegibilidade; não é MIT dos exemplos. | Alternativa só após decisão explícita e revisão das condições da versão escolhida; não fazer stack duplo padrão. |
| [OpenShorts core 89b4074](https://github.com/mutonby/openshorts/blob/89b4074986c2b5fa8ffcac862116f2d3368d4223/LICENSE) e [cloud/LICENSE](https://github.com/mutonby/openshorts/blob/89b4074986c2b5fa8ffcac862116f2d3368d4223/cloud/LICENSE) | Core MIT; diretório cloud/ usa **OpenShorts Commercial License**, explicitamente fora do MIT. | Só estudar a separação de etapas; não incorporar cloud/autopilot/billing/auth nem assumir a licença do core para todo o repo. |
| [Ultralytics ea4b382](https://github.com/ultralytics/ultralytics/blob/ea4b3829ad46748b6335d8641b6e5ac00d3e6095/LICENSE) | GNU AGPLv3 no LICENSE consultado. OpenShorts pinou ultralytics==8.4.46 em [requirements.txt](https://github.com/mutonby/openshorts/blob/89b4074986c2b5fa8ffcac862116f2d3368d4223/requirements.txt); a licença dessa versão/dependência deve ser revista antes de adoção. | Dependências/modelos não herdam MIT do projeto chamador; nenhuma inclusão neste lote. |
| [Anil-matcha 3d11f2e](https://github.com/Anil-matcha/AI-Youtube-Shorts-Generator/blob/3d11f2e6ecbbb9757d788e1bd05695c01f3e6c6c/LICENSE) | MIT. | Referência de etapas; testar offsets absolutos em vídeos longos antes de qualquer reaproveitamento. Não afirmar bug sem reprodução. Nenhum áudio enviado a backend hospedado. |
| [SeeCut 75c6ca3](https://github.com/YeJe-cpu/SeeCut/blob/75c6ca3c6ec00872ba03e8741b9a14df60dc6195/LICENSE) | **PolyForm Noncommercial License 1.0.0**, com Required Notice. | Só conceitos gerais; nenhum código/asset incorporado para uso comercial. |
| [Hypit dc2b7a8](https://github.com/hypit-ai/hypit/blob/dc2b7a8f31b1ef1443a79ca448548d69e3ceb6a0/LICENSE) | **Open Source License** do projeto: Apache 2.0 **modificada** com condições adicionais para serviço multi-tenant/hosted/SaaS, redistribuição comercial e marcas/notices; não é Apache-2.0 pura. | Não incorporar como backend SaaS/multi-tenant nem inferir permissão pelo rótulo Apache; somente conceitos gerais neste lote. |
| [OpenMontage e45f5b1](https://github.com/calesthio/OpenMontage/blob/e45f5b12bd46440b04f3675af9a77d0718e6a254/LICENSE) | GNU AGPLv3 no LICENSE consultado. | Referência conceitual, sem código/serviço novo. Experimental na triagem recebida; estabilidade não validada aqui. |

Estas identificações são documentais, por arquivo e revisão; não aprovam uma
incorporação futura nem resolvem direitos de datasets/pesos/serviços/assets.
Antes de adotar algo, fixar a versão exata do componente e revisar seus termos;
licença incompatível ou não identificada mantém o componente fora do runtime.
