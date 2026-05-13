/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import { Layout } from './components/Layout';
import { AppProvider } from './context/AppContext';

export default function App() {
  return (
    <AppProvider>
      <Layout />
    </AppProvider>
  );
}
