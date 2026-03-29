import fs from 'node:fs';
import path from 'node:path';

describe('App interpretation logging', () => {
  it('does not manually append a running interpretation log after measurement completes', () => {
    const sourcePath = path.resolve(process.cwd(), 'src/App.tsx');
    const source = fs.readFileSync(sourcePath, 'utf8');

    expect(source).not.toContain("message: 'AI interpretation in progress.'");
  });
});
