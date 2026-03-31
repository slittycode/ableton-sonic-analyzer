import fs from 'node:fs';
import path from 'node:path';

describe('main.tsx view switching', () => {
  it('wires the dense DAW concept behind the app view resolver', () => {
    const sourcePath = path.resolve(process.cwd(), 'src/main.tsx');
    const source = fs.readFileSync(sourcePath, 'utf8');

    expect(source).toMatch(/resolveAppView/);
    expect(source).toMatch(/DenseDawConcept/);
    expect(source).toMatch(/window\.location\.search/);
    expect(source).toMatch(/daw-concept/);
  });
});
