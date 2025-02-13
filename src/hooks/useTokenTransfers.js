import { useQuery } from '@tanstack/react-query';
import { fetchTokenNames } from '../api/portfolio';

export const useTokenTransfers = (walletAddress) => {
    return useQuery({
        queryKey: ['tokenTransfers', walletAddress],
        queryFn: () => fetchTokenNames(walletAddress),
        enabled: !!walletAddress,  
    });
};
