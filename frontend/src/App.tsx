/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import { Layout } from './components/Layout';
import { ImmersiveBackground } from './components/ImmersiveBackground';
import { AppProvider } from './context/AppContext';

export default function App() {
  return (
    <AppProvider>
      <ImmersiveBackground />
      <div className="relative z-10">
        <Layout />
      </div>
    </AppProvider>
  );
}
