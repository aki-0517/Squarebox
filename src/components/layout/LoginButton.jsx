import React from 'react';
import { usePrivy } from '@privy-io/react-auth';

const LoginButton = () => {
  const { login, logout, authenticated, user } = usePrivy();
  
  return (
    <div className="relative w-full">
      {authenticated ? (
        <div className="flex items-center justify-between space-x-4 bg-gray-800 px-6 py-3 rounded-lg shadow-md">

        <p className="text-lg font-semibold text-white">
          Welcome,{" "}
          <span className="text-blue-400">
            {user?.wallet?.address || "Unknown Wallet"}
          </span>
        </p>

        <button
          onClick={logout}
          className="w-30 bg-red-500 text-white px-4 py-2 rounded-lg shadow-md hover:bg-red-600 transition duration-300"
        >
          Logout
        </button>
      </div>      
      ) : (
        <div className="flex justify-center">
          <button
            onClick={() => login({ loginMethods: ['email', 'wallet'] })}
            className="bg-blue-500 text-white px-6 py-3 rounded-lg shadow-md hover:bg-blue-600 transition duration-300"
          >
            Login with Email or Wallet
          </button>
        </div>
      )}
    </div>
  );
};

export default LoginButton;
