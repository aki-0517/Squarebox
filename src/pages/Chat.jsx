import { useState, useEffect } from 'react';
import { useTokenTransfers } from '../hooks/useTokenTransfers';
import { ethers } from 'ethers';  // Wallet address validation
import MainLayout from '../components/layout/MainLayout';
import ChatInput from '../components/chat/ChatInput';
import TypingIndicator from '../components/chat/TypingIndicator';
import { v4 as uuidv4 } from 'uuid';
import TagButton from '../components/layout/TagButton';

export default function Chat() {
  console.log('Chat component rendered');
  
  const [messages, setMessages] = useState([]);
  const [isTyping, setIsTyping] = useState(false);
  const [walletAddress, setWalletAddress] = useState('');
  const [searchInput, setSearchInput] = useState('');
  const [trendingWords, setTrendingWords] = useState([]); 



  const fetchTokensFromRedis = async () => {
    try {
      const response = await fetch('http://localhost:8000/redis/tokens');
      if (!response.ok) {
        console.error("Failed to fetch tokens from Redis:", response.status, response.statusText);
        return;
      }
  
      const data = await response.json();
      if (data.tokens && Array.isArray(data.tokens)) {
        console.log("Tokens from Redis:", data.tokens);
        setTrendingWords(prev => [...new Set([...prev, ...data.tokens])]); 
      }
    } catch (err) {
      console.error("Error fetching tokens from Redis:", err);
    }
  };

  useEffect(() => {
    fetchTokensFromRedis();
  }, []);

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

    // Clear the search input after sending the message
    setSearchInput('');

    if (ethers.utils.isAddress(message)) {
      console.log('Valid wallet address detected:', message);
      setWalletAddress(message); 
      setIsTyping(true);
      return;
    } else if (message.startsWith('0x')) {
      console.log('Invalid wallet address detected:', message);
      setMessages(prev => [
        ...prev,
        {
          id: uuidv4(),
          content: "Invalid wallet address. Please enter a valid address.",
          role: 'assistant'
        }
      ]);
      return;
    }

    // 通常のAIレスポンス
    setIsTyping(true);
    setTimeout(() => {
      const aiResponse = getAIResponse(message);
      console.log('AI response generated:', aiResponse);
      setMessages(prev => [
        ...prev,
        {
          id: uuidv4(),
          content: aiResponse,
          role: 'assistant'
        }
      ]);
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

  useEffect(() => {
    console.log('Portfolio data updated:', { portfolio, isLoading, error });

    if (portfolio && !isLoading && !error) {
      setIsTyping(true);

      setTimeout(async () => {
        if (portfolio.erc20.length > 0) {
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

        if (allTokens.length > 0) {
          const advice = await fetchInvestmentAdvice(allTokens);
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
      {/* 全体の枠：Chrome風のヘッダー + 検索結果表示エリア */}
      <div className="w-full flex flex-col h-[90vh] max-w-4xl mx-auto bg-gray-50 shadow-lg rounded-lg overflow-hidden">
        {/* Chromeのアドレスバー風のヘッダー */}
        <div className="bg-gray-200 border-b border-gray-300 p-2">
          {/* 左側にある丸いボタン（戻る・進むボタン風） */}
          <div className="flex space-x-2 mb-2">
            <div className="w-3 h-3 bg-red-500 rounded-full"></div>
            <div className="w-3 h-3 bg-yellow-500 rounded-full"></div>
            <div className="w-3 h-3 bg-green-500 rounded-full"></div>
          </div>
          {/* "検索バー"としてのチャット入力 */}
          <ChatInput
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="Enter wallet address or query..."
            onSendMessage={handleSendMessage}
          />
          <div className="flex flex-wrap mt-2 space-x-2">
  {trendingWords.map((word) => (
    <TagButton key={word} tag={word} onClick={() => handleTagClick(word)} />
  ))}
</div>

        </div>

        {/* メイン表示領域：検索結果表示エリア */}
        <div className="flex-1 overflow-y-auto p-4 bg-white">
          {/* タイピングインジケータ */}
          {isTyping && <TypingIndicator />}

          {/* 検索結果リスト（assistantのメッセージのみ表示すると検索結果っぽくなる） */}
          <div className="space-y-6">
            {messages
              .filter((msg) => msg.role === 'assistant')
              .map((msg, idx) => (
                <SearchResultItem key={msg.id} index={idx} content={msg.content} />
              ))
            }
          </div>
        </div>
      </div>
    </MainLayout>
  );
}

/**
 * 検索結果っぽいカードを表示するコンポーネント。
 * index（表示順）と content（本文）を受け取り、Google検索結果のようなレイアウトを簡易再現。
 */
function SearchResultItem({ index, content }) {
  return (
    <div className="p-4 bg-white rounded-md shadow-md">
      <div className="text-sm text-gray-500">Research Result {index + 1}</div>
      <a href="#" className="text-blue-600 text-lg hover:underline">
        Result Title {index + 1}
      </a>
      <p className="mt-2 text-gray-700">{content}</p>
    </div>
  );
}
