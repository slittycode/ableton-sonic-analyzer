// Re-export shim. The Tooltip implementation moved to ./ui/Tooltip.tsx
// (Radix-backed, accessible, with collision detection). The original
// custom + Framer Motion implementation has been removed.
//
// Callers must wrap their tree in <TooltipProvider> (exported from
// ./ui/Tooltip) once at the app root before mounting any <Tooltip>.
export { Tooltip, TooltipProvider, type TooltipProps } from './ui/Tooltip';
