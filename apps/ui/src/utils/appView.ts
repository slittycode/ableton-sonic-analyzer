export type AppView = 'app' | 'daw-concept';

export function resolveAppView(search: string): AppView {
  const params = new URLSearchParams(search.startsWith('?') ? search.slice(1) : search);

  return params.get('view') === 'daw' ? 'daw-concept' : 'app';
}

export function getAppViewHref(view: AppView): string {
  return view === 'daw-concept' ? '/?view=daw' : '/';
}
