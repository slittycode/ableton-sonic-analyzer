import { assertIntegrationE2EPreflight } from './preflight';

export default async function globalSetup(): Promise<void> {
  await assertIntegrationE2EPreflight();
}
