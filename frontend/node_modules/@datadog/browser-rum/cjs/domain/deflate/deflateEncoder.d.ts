import type { DeflateEncoder, DeflateEncoderStreamId, DeflateWorker } from '@datadog/browser-core';
import type { RumConfiguration } from '@datadog/browser-rum-core';
export declare function createDeflateEncoder(configuration: RumConfiguration, worker: DeflateWorker, streamId: DeflateEncoderStreamId): DeflateEncoder;
