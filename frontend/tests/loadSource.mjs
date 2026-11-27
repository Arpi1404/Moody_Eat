// Loads a module from src/ for `node --test`. Each file is compiled with the
// compiler Vite already ships (type-only imports are dropped), and its
// relative imports are loaded the same way. Works on the Node 20 that CI uses.

import { readFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { transformWithEsbuild } from 'vite'

const built = new Map()

async function dataUrl(file) {
  if (!built.has(file.href)) {
    const { code } = await transformWithEsbuild(
      await readFile(file, 'utf8'),
      fileURLToPath(file),
      { loader: 'ts', format: 'esm' },
    )
    let linked = code
    for (const [statement, path] of code.matchAll(/from\s*["'](\.\.?\/[^"']+)["']/g)) {
      const dependency = await dataUrl(new URL(`${path}.ts`, file))
      linked = linked.replace(statement, `from "${dependency}"`)
    }
    built.set(
      file.href,
      `data:text/javascript;base64,${Buffer.from(linked).toString('base64')}`,
    )
  }
  return built.get(file.href)
}

/** `loadSource('lib/questBuild.ts')` */
export async function loadSource(path) {
  return import(await dataUrl(new URL(`../src/${path}`, import.meta.url)))
}
