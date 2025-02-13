import axios from 'axios';

const API_URL = "https://api.sonicscan.org/api";
const API_KEY = import.meta.env.VITE_SONICSCAN_API_KEY;  // Retrieve API key from environment variables

/**
 * Fetches ERC-20, ERC-721, and ERC-1155 token transfer history 
 * and extracts up to 3 unique token names for each type.
 * @param {string} walletAddress - The user's wallet address.
 * @returns {Promise<Object>} An object containing lists of token names for each type.
 */
export const fetchTokenNames = async (walletAddress) => {
    try {
        console.log(`Fetching token names for wallet: ${walletAddress}`);
        console.log(`Using API KEY: ${API_KEY ? "Set" : "Not Set"}`);

        // Logging API requests
        console.log(`Requesting ERC-20 transactions...`);
        console.log(`Requesting ERC-721 transactions...`);
        console.log(`Requesting ERC-1155 transactions...`);

        // Execute API requests concurrently
        const [erc20Response, erc721Response, erc1155Response] = await Promise.all([
            axios.get(`${API_URL}`, {
                params: {
                    module: "account",
                    action: "tokentx",
                    address: walletAddress,
                    page: 1,
                    offset: 10,  // Fetch up to 10 transactions for better accuracy
                    startblock: 0,
                    endblock: 99999999,
                    sort: "asc",
                    apikey: API_KEY
                }
            }),
            axios.get(`${API_URL}`, {
                params: {
                    module: "account",
                    action: "tokennfttx",
                    address: walletAddress,
                    page: 1,
                    offset: 10,  // Fetch up to 10 transactions for better accuracy
                    startblock: 0,
                    endblock: 99999999,
                    sort: "asc",
                    apikey: API_KEY
                }
            }),
            axios.get(`${API_URL}`, {
                params: {
                    module: "account",
                    action: "token1155tx",
                    address: walletAddress,
                    page: 1,
                    offset: 10,  // Fetch up to 10 transactions for better accuracy
                    startblock: 0,
                    endblock: 99999999,
                    sort: "asc",
                    apikey: API_KEY
                }
            })
        ]);

        // Logging API responses
        console.log(`ERC-20 Response:`, erc20Response.data);
        console.log(`ERC-721 Response:`, erc721Response.data);
        console.log(`ERC-1155 Response:`, erc1155Response.data);

        // Extract unique token names (limit to 3 per category)
        const erc20Tokens = [...new Set(erc20Response.data.result?.map(tx => tx.tokenName) || [])].slice(0, 3);
        const erc721Tokens = [...new Set(erc721Response.data.result?.map(tx => tx.tokenName) || [])].slice(0, 3);
        const erc1155Tokens = [...new Set(erc1155Response.data.result?.map(tx => tx.tokenName) || [])].slice(0, 3);

        console.log(`Extracted ERC-20 Tokens:`, erc20Tokens);
        console.log(`Extracted ERC-721 Tokens:`, erc721Tokens);
        console.log(`Extracted ERC-1155 Tokens:`, erc1155Tokens);

        return {
            erc20: erc20Tokens,
            erc721: erc721Tokens,
            erc1155: erc1155Tokens
        };
    } catch (error) {
        console.error("Error fetching token names:", error);

        if (error.response) {
            console.error(`API Error - Status: ${error.response.status}, Data:`, error.response.data);
        } else {
            console.error(`Error Message: ${error.message}`);
        }

        throw error;
    }
};
