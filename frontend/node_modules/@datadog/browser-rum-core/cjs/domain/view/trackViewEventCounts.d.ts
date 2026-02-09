import type { LifeCycle } from '../lifeCycle';
export declare function trackViewEventCounts(lifeCycle: LifeCycle, viewId: string, onChange: () => void): {
    stop: () => void;
    eventCounts: import("../trackEventCounts").EventCounts;
};
