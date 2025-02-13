import { useState, useEffect } from 'react';
import { useTokenTransfers } from '../hooks/useTokenTransfers';
import { ethers } from 'ethers';  // Wallet address validation
import MainLayout from '../components/layout/MainLayout';
import ChatHistory from '../components/chat/ChatHistory';
import ChatInput from '../components/chat/ChatInput';
import TypingIndicator from '../components/chat/TypingIndicator';

export default function Chat() {
  const [messages, setMessages] = useState([]);
  const [isTyping, setIsTyping] = useState(false);
  const [walletAddress, setWalletAddress] = useState('');
  
  // Custom hook for fetching portfolio data
  const { data: portfolio, error, isLoading } = useTokenTransfers(walletAddress);

  const mockAIResponses = {
    hello: "Hello! How can I assist you today?",
    default: "I see. Could you tell me more about that?",
    help: "I'm here to help! What would you like to know?",
    thanks: "You're welcome! Do you have any other questions?",
    bye: "Goodbye! Have a great day!",
  };

  const getAIResponse = (userMessage) => {
    const lowercaseMsg = userMessage.toLowerCase();

    if (lowercaseMsg.includes('hello') || lowercaseMsg.includes('hi')) {
      return mockAIResponses.hello;
    } else if (lowercaseMsg.includes('help')) {
      return mockAIResponses.help;
    } else if (lowercaseMsg.includes('thank')) {
      return mockAIResponses.thanks;
    } else if (lowercaseMsg.includes('bye')) {
      return mockAIResponses.bye;
    }
    return mockAIResponses.default;
  };

  const handleSendMessage = (message) => {
    setMessages(prev => [...prev, { id: Date.now(), content: message, role: 'user' }]);

    // Validate wallet address
    if (ethers.utils.isAddress(message)) {
      setWalletAddress(message); // Set wallet address if valid
      setIsTyping(true);

      setTimeout(() => {
        setMessages(prev => [...prev, { id: Date.now(), content: "Wallet address detected. Fetching portfolio data...", role: 'assistant' }]);
      }, 1000);
      
      return;
    } else if (message.startsWith('0x')) {
      // Looks like a wallet address but invalid
      setMessages(prev => [...prev, { id: Date.now(), content: "Invalid wallet address. Please enter a valid address.", role: 'assistant' }]);
      return;
    }

    // Default AI response
    setIsTyping(true);
    setTimeout(() => {
      const aiResponse = getAIResponse(message);
      setMessages(prev => [...prev, { id: Date.now(), content: aiResponse, role: 'assistant' }]);
      setIsTyping(false);
    }, 1000);
  };

  // Add portfolio data when available
  useEffect(() => {
    if (portfolio && !isLoading && !error) {
      setIsTyping(true);

      setTimeout(() => {
        setMessages(prev => [...prev, { id: Date.now(), content: `Portfolio data retrieved.`, role: 'assistant' }]);

        if (portfolio.erc20.length > 0) {
          setMessages(prev => [
            ...prev,
            { id: Date.now(), content: `ERC-20 Tokens: ${portfolio.erc20.join(', ')}`, role: 'assistant' }
          ]);
        }

        if (portfolio.erc721.length > 0) {
          setMessages(prev => [
            ...prev,
            { id: Date.now(), content: `ERC-721 NFTs: ${portfolio.erc721.join(', ')}`, role: 'assistant' }
          ]);
        }

        if (portfolio.erc1155.length > 0) {
          setMessages(prev => [
            ...prev,
            { id: Date.now(), content: `ERC-1155 Tokens: ${portfolio.erc1155.join(', ')}`, role: 'assistant' }
          ]);
        }

        setIsTyping(false);
      }, 1500);
    }
  }, [portfolio, isLoading, error]);

  // Handle API error
  useEffect(() => {
    if (error) {
      setMessages(prev => [...prev, { id: Date.now(), content: "Failed to fetch portfolio data. Please try again.", role: 'assistant' }]);
      setIsTyping(false);
    }
  }, [error]);

  return (
    <MainLayout>
      <div className="flex flex-col h-[90vh] max-w-3xl w-full mx-auto bg-white shadow-lg rounded-lg overflow-hidden">
        <div className="flex-1 overflow-y-auto p-6 space-y-4 bg-gray-100">
          <ChatHistory messages={messages} />
          {isTyping && <TypingIndicator />}
        </div>

        <div className="border-t border-gray-300 bg-white p-4">
          <ChatInput onSendMessage={handleSendMessage} />
        </div>
      </div>
    </MainLayout>
  );
}
