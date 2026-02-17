import React from 'react';
import IntegrationHub from './IntegrationHub';

interface IntegrationSettingsProps {
  onBack: () => void;
}

const IntegrationSettings: React.FC<IntegrationSettingsProps> = ({ onBack }) => {
  return <IntegrationHub onBack={onBack} />;
};

export default IntegrationSettings;
