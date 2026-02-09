import type { Click } from './trackClickActions';
export interface ClickChain {
    tryAppend: (click: Click) => boolean;
    stop: () => void;
}
export declare const MAX_DURATION_BETWEEN_CLICKS = 1000;
export declare const MAX_DISTANCE_BETWEEN_CLICKS = 100;
export declare function createClickChain(firstClick: Click, onFinalize: (clicks: Click[]) => void): ClickChain;
