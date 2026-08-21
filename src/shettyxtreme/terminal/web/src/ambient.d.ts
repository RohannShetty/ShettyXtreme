declare module "d3-force" {
  export function forceSimulation<T>(nodes?: T[]): Simulation<T>;
  export function forceLink<T, L>(links?: L[]): SimulationLinkForce<T, L>;
  export function forceManyBody(): SimulationForce;
  export function forceCenter<T>(x: number, y: number): SimulationForce;
  export function forceCollide<T>(): CollideForce<T>;
  export interface Simulation<T> {
    force(name: string, f: SimulationForce | null): Simulation<T>;
    alphaDecay(v: number): Simulation<T>;
    alphaTarget(v: number): Simulation<T>;
    alpha(v: number): Simulation<T>;
    restart(): Simulation<T>;
    stop(): void;
    tick(): void;
    on(event: string, fn: () => void): Simulation<T>;
  }
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  export type SimulationForce = any;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  export type SimulationLinkForce<T, L> = any;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  export type CollideForce<T> = any;
}
declare module "d3-selection" {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  export function select<T = any>(el: unknown): Selection<T>;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  export type Selection<T = any> = any;
}
declare module "d3-zoom" {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  export function zoom<E = any, R = any>(): ZoomBehavior<E, R>;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  export type ZoomBehavior<E = any, R = any> = any;
}
declare module "d3-drag" {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  export function drag<E = any, D = any>(): DragBehavior<E, D>;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  export type DragBehavior<E = any, D = any> = any;
}
