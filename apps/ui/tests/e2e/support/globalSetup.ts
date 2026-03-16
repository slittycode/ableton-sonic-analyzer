import { assertLiveE2EPreflight } from './preflight';

export default async function globalSetup(): Promise<void> {
  await assertLiveE2EPreflight();
}
