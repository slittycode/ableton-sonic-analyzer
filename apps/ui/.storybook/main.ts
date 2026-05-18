import type { StorybookConfig } from '@storybook/react-vite';

const config: StorybookConfig = {
  framework: '@storybook/react-vite',
  stories: ['../src/**/*.stories.@(ts|tsx)'],
  addons: ['@storybook/addon-a11y'],
  // Reapply the Tailwind v4 plugin so Storybook sees the @theme tokens from
  // src/index.css. The app uses @tailwindcss/vite; Storybook's standalone Vite
  // pipeline does not pick that up by default.
  viteFinal: async (vite) => {
    const { default: tailwindcss } = await import('@tailwindcss/vite');
    vite.plugins = [...(vite.plugins ?? []), tailwindcss()];
    return vite;
  },
};

export default config;
