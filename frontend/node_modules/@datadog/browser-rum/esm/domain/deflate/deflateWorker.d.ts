import type { DeflateWorker } from '@datadog/browser-core';
import type { RumConfiguration } from '@datadog/browser-rum-core';
export declare const INITIALIZATION_TIME_OUT_DELAY: number;
/**
 * In order to be sure that the worker is correctly working, we need a round trip of
 * initialization messages, making the creation asynchronous.
 * These worker lifecycle states handle this case.
 */
export declare const enum DeflateWorkerStatus {
    Nil = 0,
    Loading = 1,
    Error = 2,
    Initialized = 3
}
export type CreateDeflateWorker = typeof createDeflateWorker;
declare function createDeflateWorker(configuration: RumConfiguration): DeflateWorker;
export declare function startDeflateWorker(configuration: RumConfiguration, source: string, onInitializationFailure: () => void, createDeflateWorkerImpl?: typeof createDeflateWorker): DeflateWorker | undefined;
export declare function resetDeflateWorkerState(): void;
export declare function getDeflateWorkerStatus(): DeflateWorkerStatus;
/**
 * Starts the deflate worker and handle messages and errors
 *
 * The spec allow browsers to handle worker errors differently:
 * - Chromium throws an exception
 * - Firefox fires an error event
 *
 * more details: https://bugzilla.mozilla.org/show_bug.cgi?id=1736865#c2
 */
export declare function doStartDeflateWorker(configuration: RumConfiguration, source: string, createDeflateWorkerImpl?: typeof createDeflateWorker): void;
export {};
