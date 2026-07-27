#!/usr/bin/env node
/**
 * Reduz a capa antes de ela subir para o Ghost.
 *
 * O gerador devolve PNG, e PNG é formato para gráfico com área chapada, não
 * para fotografia: a capa de 1536×1024 saía com 2,3 MB, e mesmo a variante de
 * 750px que o Ghost gera ficava em 665 KB. Três dessas na home do blog são
 * 2 MB só de imagem — foi o que derrubou a performance de 83 para 78 no
 * Lighthouse, com 2.532 KiB apontados como desperdício.
 *
 * A mesma imagem em WebP fica na casa das dezenas de KB, sem diferença
 * perceptível numa thumbnail.
 *
 * Uso:  node otimizar_imagem.js <entrada> <saida.webp> [largura] [qualidade]
 * Saída (stdout, JSON): {"ok":true,"antes":N,"depois":N,"reducao_pct":N,...}
 */
'use strict';

const { statSync } = require('fs');
const { execFileSync } = require('child_process');
const path = require('path');

/** Resolve o sharp: local primeiro, depois o prefixo global do npm. */
function carregarSharp() {
  try { return require('sharp'); } catch (_) { /* segue para o global */ }
  try {
    const raiz = execFileSync('npm', ['root', '-g'], { encoding: 'utf8' }).trim();
    return require(path.join(raiz, 'sharp'));
  } catch (_) {
    return null;
  }
}

const LARGURA_PADRAO = 1600;   // acima disso não há ganho visível em capa
const QUALIDADE_PADRAO = 82;   // onde o artefato ainda não aparece em foto

async function main() {
  const [entrada, saida, larguraArg, qualidadeArg] = process.argv.slice(2);
  if (!entrada || !saida) {
    console.log(JSON.stringify({ ok: false, erro: 'uso: otimizar_imagem.js <entrada> <saida> [largura] [qualidade]' }));
    process.exit(2);
  }

  // O sharp está instalado GLOBALMENTE na imagem (o Read do CLI precisa dele),
  // e `require` só olha os node_modules acima do próprio script. Sem consultar
  // o prefixo global, o require falha mesmo com o pacote presente na máquina.
  const sharp = carregarSharp();
  if (!sharp) {
    // Sem sharp, quem chama segue com o arquivo original: capa pesada é ruim,
    // capa nenhuma é pior.
    console.log(JSON.stringify({ ok: false, erro: 'sharp indisponível' }));
    process.exit(3);
  }

  const largura = parseInt(larguraArg, 10) || LARGURA_PADRAO;
  const qualidade = parseInt(qualidadeArg, 10) || QUALIDADE_PADRAO;

  try {
    const antes = statSync(entrada).size;
    const meta = await sharp(entrada).metadata();

    const info = await sharp(entrada)
      .resize({
        width: largura,
        // `withoutEnlargement`: imagem menor que o alvo não é esticada, o que
        // só somaria peso e borrão.
        withoutEnlargement: true,
        fit: 'inside',   // preserva a proporção; nunca corta nem distorce
      })
      .webp({ quality: qualidade, effort: 5 })
      .toFile(saida);

    const depois = statSync(saida).size;
    console.log(JSON.stringify({
      ok: true,
      antes,
      depois,
      reducao_pct: Math.round((1 - depois / antes) * 100),
      largura_original: meta.width,
      largura_final: info.width,
      altura_final: info.height,
      formato: 'webp',
    }));
  } catch (e) {
    console.log(JSON.stringify({ ok: false, erro: String(e.message || e) }));
    process.exit(1);
  }
}

main();
