import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './index.css';

import { datadogRum } from '@datadog/browser-rum';
import { reactPlugin } from '@datadog/browser-rum-react';
console.log('✅ Step 1: Import =', typeof datadogRum)

datadogRum.init({
    applicationId: 'f8e9a06b-756a-4009-94a8-642e8351da8b',
    clientToken: 'pub5ae3209ecbdf2c1ea986becacef23d27',
    site: 'datadoghq.com',
    service:'ai-sre-app-ui',
    env: 'prod',
    
    // Specify a version number to identify the deployed version of your application in Datadog
    // version: '1.0.0',
    sessionSampleRate:  100,
    sessionReplaySampleRate: 100,
    defaultPrivacyLevel: 'mask-user-input',
    plugins: [reactPlugin({ router: false })],
});
window.DD_RUM_INITIALIZED = true
window.datadogRum = datadogRum 
console.log('✅ Datadog initialized')
console.log('✅ Step 2: Initialized')


ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);

declare global {
  interface Window {
    DD_RUM_INITIALIZED?: boolean
    datadogRum?: typeof datadogRum
  }
}


