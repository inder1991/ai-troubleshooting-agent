import type { RumActionEvent, RumErrorEvent, RumLongTaskEvent, RumResourceEvent } from '../rumEvent.types';
import type { LifeCycle } from './lifeCycle';
export interface EventCounts {
    errorCount: number;
    actionCount: number;
    longTaskCount: number;
    resourceCount: number;
    frustrationCount: number;
}
export declare function trackEventCounts({ lifeCycle, isChildEvent, onChange: callback, }: {
    lifeCycle: LifeCycle;
    isChildEvent: (event: RumActionEvent | RumErrorEvent | RumLongTaskEvent | RumResourceEvent) => boolean;
    onChange?: () => void;
}): {
    stop: () => void;
    eventCounts: EventCounts;
};
