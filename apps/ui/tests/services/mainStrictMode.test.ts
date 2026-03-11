import fs from 'node:fs';
import path from 'node:path';

describe('main.tsx bootstrap', () => {
  it('does not wrap App in React StrictMode', () => {
    const sourcePath = path.resolve(process.cwd(), 'src/main.tsx');
    const source = fs.readFileSync(sourcePath, 'utf8');

    expect(source).not.toMatch(/<StrictMode>/);
    expect(source).not.toMatch(/import\s*\{\s*StrictMode\s*\}\s*from\s*'react'/);
  });
});
