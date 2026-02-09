import type { Click } from './trackClickActions';
export declare function computeFrustration(clicks: Click[], rageClick: Click): {
    isRage: boolean;
};
export declare function isRage(clicks: Click[]): boolean;
export declare function isDead(click: Click): boolean;
