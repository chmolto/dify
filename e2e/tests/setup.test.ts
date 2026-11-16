import { mkdtemp, readFile, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vite-plus/test'
import { dockerDir, middlewareComposeFile, runCommandOrThrow } from '../scripts/common.ts'
import { captureMiddlewareLogs } from '../scripts/setup.ts'

vi.mock('../scripts/env-register.ts', () => ({}))
vi.mock('../scripts/common.ts', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../scripts/common.ts')>()),
  isMainModule: () => false,
  runCommandOrThrow: vi.fn(),
}))

describe('middleware log capture', () => {
  let logDir: string

  beforeEach(async () => {
    vi.resetAllMocks()
    logDir = await mkdtemp(join(tmpdir(), 'dify-middleware-logs-'))
  })
  afterEach(async () => {
    vi.restoreAllMocks()
    await rm(logDir, { recursive: true, force: true })
  })

  it('saves timestamped logs with the same Compose file and profiles as middleware startup', async () => {
    vi.mocked(runCommandOrThrow).mockResolvedValue({
      exitCode: 0,
      stdout: 'daemon logs\n',
      stderr: 'warnings\n',
    })
    const logPath = join(logDir, 'cucumber-middleware.log')
    await captureMiddlewareLogs(logPath)

    expect(runCommandOrThrow).toHaveBeenCalledWith({
      command: 'docker',
      args: [
        'compose',
        '-f',
        middlewareComposeFile,
        '--profile',
        'postgresql',
        '--profile',
        'weaviate',
        'logs',
        '--no-color',
        '--timestamps',
      ],
      cwd: dockerDir,
      stdio: 'pipe',
    })
    expect(await readFile(logPath, 'utf8')).toBe('daemon logs\nwarnings\n')
  })

  it.each(['command', 'write'])(
    'warns and resolves when %s fails so teardown can continue',
    async (failure) => {
      const warning = vi.spyOn(console, 'warn').mockImplementation(() => {})
      vi.mocked(runCommandOrThrow).mockResolvedValue({ exitCode: 0, stdout: 'logs', stderr: '' })
      if (failure === 'command')
        vi.mocked(runCommandOrThrow).mockRejectedValueOnce(new Error('Docker unavailable'))

      const logPath = join(logDir, 'missing-parent', 'cucumber-middleware.log')
      await expect(captureMiddlewareLogs(logPath)).resolves.toBeUndefined()
      expect(warning).toHaveBeenCalledOnce()
      expect(warning).toHaveBeenCalledWith('Failed to capture middleware logs:', expect.any(Error))
    },
  )
})
