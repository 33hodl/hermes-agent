import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { load, loadAll } from 'js-yaml'
import { expect, test } from 'vitest'

const repo = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const semver = createRequire(import.meta.url)('semver')
const lock = loadAll(readFileSync(resolve(repo, 'pnpm-lock.yaml'), 'utf8'))[0]
const workspace = load(readFileSync(resolve(repo, 'pnpm-workspace.yaml'), 'utf8'))

// Advisories fixed only in a new major, so the fix has to be an `overrides` entry:
//  - GHSA-3g3m-2fjr-6pw4: glob's AbortSignal cancellation bypass, fixed in 14.0.2 (no 9-13 fix)
//  - GHSA-g3hv-75wg-m249: minimatch globparts amplification DoS, fixed in 11.0.1 (no 7-10 fix)
const advisories = [
  {
    name: 'glob',
    vulnerable: '>=9.0.0 <=14.0.1',
    // glob 7 stays: node-gyp 10 and @electron/asar 3 call the CommonJS API glob 13/14 dropped.
    legacy: '^7.0.0',
  },
  {
    name: 'minimatch',
    vulnerable: '>=7.0.0 <11.0.1',
    // minimatch 3 and 5 stay: filelist and glob 7 call the bare function/CommonJS export.
    legacy: '^3.0.0 || ^5.0.0',
  },
]

const lockedVersions = name =>
  Object.keys(lock.packages ?? {})
    .filter(key => key.startsWith(`${name}@`))
    .map(key => key.slice(name.length + 1))

test.each(advisories)('$name resolves off every vulnerable version', ({ name, vulnerable }) => {
  const offenders = lockedVersions(name).filter(version => semver.satisfies(version, vulnerable))
  expect(offenders).toEqual([])
})

test.each(advisories)('$name keeps the majors its CommonJS consumers need', ({ name, legacy }) => {
  const kept = lockedVersions(name).filter(version => semver.satisfies(version, legacy))
  expect(kept.length).toBeGreaterThan(0)
})

// A bare `glob:`/`minimatch:` override lifts the fix across the whole tree, including glob 7 and
// minimatch 3/5, which resolve above and call APIs those majors no longer export. Every override
// range must sit inside the advisory's vulnerable range, so only exposed consumers move.
test.each(advisories)('$name override covers the vulnerable ranges and nothing else', ({ name, vulnerable }) => {
  const keys = Object.keys(workspace.overrides ?? {}).filter(key => key === name || key.startsWith(`${name}@`))
  expect(keys).not.toContain(name)
  expect(keys.length).toBeGreaterThan(0)
  const outside = keys.map(key => key.slice(name.length + 1)).filter(range => !semver.subset(range, vulnerable))
  expect(outside).toEqual([])
})
