import type { BrowserIncrementalData, BrowserIncrementalSnapshotRecord } from '../../types';
export declare function assembleIncrementalSnapshot<Data extends BrowserIncrementalData>(source: Data['source'], data: Omit<Data, 'source'>): BrowserIncrementalSnapshotRecord;
