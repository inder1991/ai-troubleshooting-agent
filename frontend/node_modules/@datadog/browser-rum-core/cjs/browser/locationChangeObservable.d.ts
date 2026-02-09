import { Observable } from '@datadog/browser-core';
import type { RumConfiguration } from '../domain/configuration';
export interface LocationChange {
    oldLocation: Readonly<Location>;
    newLocation: Readonly<Location>;
}
export declare function createLocationChangeObservable(configuration: RumConfiguration, location: Location): Observable<LocationChange>;
