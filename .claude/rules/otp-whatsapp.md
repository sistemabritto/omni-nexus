# OTP por WhatsApp — o endpoint que pode custar o seu número

Autenticação por código enviado no WhatsApp é a melhor conversão que existe no
Brasil: sem senha, sem e-mail que cai em spam, e o "oi" do usuário já cria o
lead no CRM. Também é o endpoint mais perigoso que um produto pode expor.

**Leia antes de escrever qualquer rota que dispare mensagem a partir de input
do usuário.**

## Por que o risco aqui é diferente

Num OTP por SMS, abuso custa dinheiro: cada disparo tem tarifa. Num OTP por
WhatsApp com instância própria, abuso custa **o ativo**: o WhatsApp bane número
que dispara mensagem para desconhecidos em volume. Um atacante que rode um
laço no seu `/otp/send` com números aleatórios não está gastando seu saldo —
está **fazendo seu número ser banido**, e com ele o histórico de conversas, os
grupos e o canal de atendimento inteiro.

Recuperar chip é dias. Recuperar reputação de número banido, às vezes nunca.

Por isso as proteções abaixo não são "boas práticas" — são a diferença entre
um endpoint e uma arma apontada para o próprio pé.

## O mínimo obrigatório

### 1. Validar o número ANTES de qualquer envio

Formato E.164, DDI permitido por allowlist (se você só atende Brasil, aceite
só `+55`), DDD válido, tamanho correto. Número que não passa não vira envio —
nem para "testar se existe".

Sem isso, o endpoint dispara para números internacionais aleatórios, que é
exatamente o padrão que aciona a detecção de spam do WhatsApp.

### 2. Rate limit em três camadas, não uma

| Camada | Limite sugerido | O que impede |
|---|---|---|
| **Por número** | 3 envios / hora, 5 / dia | alguém usar seu endpoint para incomodar uma pessoa específica |
| **Por IP** | 10 envios / hora | o laço trivial |
| **Global (a instância)** | teto absoluto por hora | o ataque distribuído que fura as duas primeiras |

A terceira é a que salva o número, e é a que quase todo mundo esquece. IP se
troca com VPN e CGNAT junta milhares de usuários atrás do mesmo endereço —
rate limit por IP sozinho é decorativo. **O teto global é o disjuntor**: ao
estourar, o sistema para de enviar e alerta, mesmo que isso derrube logins
legítimos por alguns minutos. Login indisponível por 10 minutos é incidente;
número banido é prejuízo permanente.

### 3. Cooldown entre reenvios

Mínimo **60 segundos** antes de permitir reenviar para o mesmo número, com
backoff crescente a cada reenvio (60s → 120s → 300s). O botão "não recebi,
reenviar" é o vetor mais usado, porque parece legítimo.

### 4. O código

- **6 dígitos, de fonte criptográfica** (`secrets` no Python, `crypto` no Node).
  Nunca `Math.random()`, nunca derivado de timestamp — os dois são previsíveis
  e transformam brute force em cálculo.
- **Expira em 5 minutos.** Código de OTP que vive uma hora é senha fraca.
- **Máximo 5 tentativas de verificação**, depois o código morre e exige novo
  envio (respeitando o cooldown). Sem esse limite, 6 dígitos são 1 milhão de
  combinações que um script testa em minutos.
- **Uso único**: consumir na primeira validação bem-sucedida.
- **Gerar novo invalida o anterior.** Dois códigos válidos ao mesmo tempo
  dobram a superfície sem nenhum ganho.
- **Comparação em tempo constante** (`secrets.compare_digest` / `timingSafeEqual`).

### 5. Nunca revelar se o número existe

A resposta do `send` é idêntica para número cadastrado e não cadastrado —
mesmo texto, mesmo status, e de preferência mesmo tempo de resposta. Diferenciar
transforma o endpoint num verificador de base: o atacante descobre quais dos
seus clientes estão cadastrados sem nunca logar.

### 6. Alertar quando o limite dispara

Rate limit atingido não é evento de rotina — é sinal. Registre e mande alerta
(Telegram, no caso do OmniNexus). Um pico de bloqueios às 3h da manhã é a única
chance de reagir antes de o WhatsApp reagir por você.

## O que NÃO resolve

- **Só CAPTCHA.** Ajuda contra bot burro, não contra ataque com resolver pago,
  e piora conversão no celular — que é onde está 100% do seu público de OTP.
- **Só rate limit por IP.** Ver acima.
- **Confiar no cliente.** Toda validação de número, cooldown e contagem que
  viva no front é sugestão, não controle. O atacante chama a API direto.

## Checklist de revisão

Antes de subir qualquer rota de OTP, confirme que existe teste automatizado
para cada linha:

- [ ] número em formato inválido → recusado sem envio
- [ ] DDI fora da allowlist → recusado sem envio
- [ ] 4º envio para o mesmo número na mesma hora → bloqueado
- [ ] reenvio antes de 60s → bloqueado com o tempo restante
- [ ] teto global atingido → para de enviar e alerta
- [ ] código expirado → recusado
- [ ] 6ª tentativa de verificação → código invalidado
- [ ] código já usado → recusado
- [ ] número inexistente e número existente → resposta idêntica
- [ ] código gerado com fonte criptográfica (teste de distribuição, não de valor)

## Regras relacionadas

- `integrations.md` — Evolution API / Evolution Go
- `tickets.md` — abuso detectado vira ticket, não só linha de log
