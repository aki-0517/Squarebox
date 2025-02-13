import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
import { PrivyProvider } from '@privy-io/react-auth';

const appId = import.meta.env.VITE_PRIVY_APP_ID;

createRoot(document.getElementById('root')).render(
  <StrictMode>
   <PrivyProvider appId={appId}
    config={{
      appearance: {
        loginMethods: ['email', 'wallet', 'google', 'apple', 'farcaster'], 
        theme: 'light',
        accentColor: '#676FFF',
      },
      externalWallets: { 
        coinbaseWallet: { 
          // Valid connection options include 'all' (default), 'eoaOnly', or 'smartWalletOnly'
          connectionOptions: 'smartWalletOnly', 
        }, 
      }, 
      embeddedWallets: {
        createOnLogin: 'users-without-wallets',
      },
    }}>
    <App />
  </PrivyProvider>
  </StrictMode>,
)
