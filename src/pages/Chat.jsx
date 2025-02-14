import { useState, useEffect } from 'react';
import { useTokenTransfers } from '../hooks/useTokenTransfers';
import { ethers } from 'ethers';  // Wallet address validation
import MainLayout from '../components/layout/MainLayout';
import ChatHistory from '../components/chat/ChatHistory';
import ChatInput from '../components/chat/ChatInput';
import TypingIndicator from '../components/chat/TypingIndicator';
import { v4 as uuidv4 } from 'uuid';

export default function Chat() {
  console.log('Chat component rendered');
  
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
    console.log('Getting AI response for message:', userMessage);
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
    console.log('Handling new message:', message);
    setMessages(prev => [...prev, { id: uuidv4(), content: message, role: 'user' }]);

    // Validate wallet address
    if (ethers.utils.isAddress(message)) {
      console.log('Valid wallet address detected:', message);
      setWalletAddress(message); // Set wallet address if valid
      setIsTyping(true);

      setTimeout(() => {
        setMessages(prev => [...prev, {
          id: uuidv4(),
          content: "Wallet address detected. Fetching portfolio data...",
          role: 'assistant'
        }]);
      }, 1000);

      return;
    } else if (message.startsWith('0x')) {
      console.log('Invalid wallet address detected:', message);
      // Looks like a wallet address but invalid
      setMessages(prev => [...prev, {
        id: uuidv4(),
        content: "Invalid wallet address. Please enter a valid address.",
        role: 'assistant'
      }]);
      return;
    }

    // Default AI response
    setIsTyping(true);
    setTimeout(() => {
      const aiResponse = getAIResponse(message);
      console.log('AI response generated:', aiResponse);
      setMessages(prev => [...prev, {
        id: uuidv4(),
        content: aiResponse,
        role: 'assistant'
      }]);
      setIsTyping(false);
    }, 1000);
  };

  const fetchInvestmentAdvice = async (tokens) => {
    console.log('Fetching investment advice for tokens:', tokens);
    try {
      const userMessage = `I want information for the following tokens: ${tokens.join(', ')}`;
      console.log('Sending request to investment advice API with message:', userMessage);
      
      const response = await fetch('http://localhost:8000/v1/chat/completions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          messages: [{ role: 'user', content: userMessage }],
          max_tokens: 1024,
          temperature: 0.7,
          stream: false
        })
      });
      
      if (!response.ok) {
        console.error("API error response:", response.status, response.statusText);
        return "Error fetching investment advice.";
      }
      
      const data = await response.json();
      console.log("Investment advice API response:", data);

      const advice = data?.choices?.[0]?.message?.content;
      console.log("Extracted advice:", advice);
      return advice || "No advice was returned.";
    } catch (err) {
      console.error("Investment advice fetch error:", err);
      return "Error fetching investment advice.";
    }
  };

  // Portfolio data update effect
  useEffect(() => {
    console.log('Portfolio data updated:', { portfolio, isLoading, error });
    
    if (portfolio && !isLoading && !error) {
      setIsTyping(true);

      setTimeout(async () => {
        console.log('Processing portfolio data');
        setMessages(prev => [
          ...prev,
          { id: uuidv4(), content: `Portfolio data retrieved.`, role: 'assistant' }
        ]);

        if (portfolio.erc20.length > 0) {
          console.log('ERC-20 tokens found:', portfolio.erc20);
          setMessages(prev => [
            ...prev,
            {
              id: uuidv4(),
              content: `ERC-20 Tokens: ${portfolio.erc20.join(', ')}`,
              role: 'assistant'
            }
          ]);
        }

        if (portfolio.erc721.length > 0) {
          console.log('ERC-721 NFTs found:', portfolio.erc721);
          setMessages(prev => [
            ...prev,
            {
              id: uuidv4(),
              content: `ERC-721 NFTs: ${portfolio.erc721.join(', ')}`,
              role: 'assistant'
            }
          ]);
        }

        if (portfolio.erc1155.length > 0) {
          console.log('ERC-1155 tokens found:', portfolio.erc1155);
          setMessages(prev => [
            ...prev,
            {
              id: uuidv4(),
              content: `ERC-1155 Tokens: ${portfolio.erc1155.join(', ')}`,
              role: 'assistant'
            }
          ]);
        }

        const allTokens = [
          ...portfolio.erc20,
          ...portfolio.erc721,
          ...portfolio.erc1155
        ];

        console.log('Combined token list:', allTokens);

        if (allTokens.length > 0) {
          const advice = await fetchInvestmentAdvice(allTokens);
          console.log('Investment advice received:', advice);
          setMessages(prev => [
            ...prev,
            {
              id: uuidv4(),
              content: advice,
              role: 'assistant'
            }
          ]);
        }

        setIsTyping(false);
      }, 1500);
    }
  }, [portfolio, isLoading, error]);

  // Error handling effect
  useEffect(() => {
    if (error) {
      console.error('Portfolio data fetch error:', error);
      setMessages(prev => [
        ...prev,
        { id: uuidv4(), content: "Failed to fetch portfolio data. Please try again.", role: 'assistant' }
      ]);
      setIsTyping(false);
    }
  }, [error]);

  console.log('Current component state:', { messages, isTyping, walletAddress });

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