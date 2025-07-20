import { useEffect, useState } from 'react';
import { Box, Typography, TextField, Button, Alert, Paper, Divider, Stack, List, ListItem, ListItemText, CircularProgress, Grid } from '@mui/material';
import axios from 'axios';

function PriceManagement() {
  const [percent, setPercent] = useState('');
  const [discount, setDiscount] = useState('');
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState('');
  const [error, setError] = useState('');
  const [productCount, setProductCount] = useState(null);
  const [priceHistory, setPriceHistory] = useState([]);
  const [undoLoading, setUndoLoading] = useState(false);
  const [resetLoading, setResetLoading] = useState(false);
  const [discountLoading, setDiscountLoading] = useState(false);
  const [products, setProducts] = useState([]);
  const [rangeStats, setRangeStats] = useState([]);
  const [topExpensive, setTopExpensive] = useState([]);
  const [topCheap, setTopCheap] = useState([]);

  // Fetch product count and all products on mount
  useEffect(() => {
    axios.get('/api/products?page=1&per_page=1000').then(res => {
      setProductCount(res.data.total);
      setProducts(res.data.items);
    });
    fetchPriceHistory();
  }, []);

  useEffect(() => {
    if (products.length > 0) {
      // Price range stats
      const ranges = [
        { label: '< $50', min: 0, max: 50 },
        { label: '$50 - $100', min: 50, max: 100 },
        { label: '$100 - $500', min: 100, max: 500 },
        { label: '$500+', min: 500, max: Infinity }
      ];
      const stats = ranges.map(r => ({
        label: r.label,
        count: products.filter(p => p.price >= r.min && p.price < r.max).length
      }));
      setRangeStats(stats);
      // Top 5 expensive/cheap
      const sorted = [...products].sort((a, b) => b.price - a.price);
      setTopExpensive(sorted.slice(0, 5));
      setTopCheap(sorted.slice(-5).reverse());
    }
  }, [products]);

  const fetchPriceHistory = async () => {
    const res = await axios.get('/api/products/price-history');
    setPriceHistory(res.data.history || []);
  };

  const handlePercentSubmit = async (e) => {
    e.preventDefault();
    setSuccess(''); setError(''); setLoading(true);
    try {
      await axios.post('/api/products/bulk-update-prices', { percent: parseFloat(percent) });
      setSuccess('Prices updated successfully.');
      fetchPriceHistory();
    } catch (err) {
      setError(err.response?.data?.error || 'An error occurred');
    }
    setLoading(false);
  };

  const handleDiscountSubmit = async (e) => {
    e.preventDefault();
    setSuccess(''); setError(''); setDiscountLoading(true);
    try {
      await axios.post('/api/products/bulk-discount', { amount: parseFloat(discount) });
      setSuccess('Discount applied successfully.');
      fetchPriceHistory();
    } catch (err) {
      setError(err.response?.data?.error || 'An error occurred');
    }
    setDiscountLoading(false);
  };

  const handleReset = async () => {
    setSuccess(''); setError(''); setResetLoading(true);
    try {
      await axios.post('/api/products/reset-prices');
      setSuccess('All prices reset to original sample values.');
      fetchPriceHistory();
    } catch (err) {
      setError(err.response?.data?.error || 'An error occurred');
    }
    setResetLoading(false);
  };

  const handleUndo = async () => {
    setSuccess(''); setError(''); setUndoLoading(true);
    try {
      await axios.post('/api/products/undo-last-price-change');
      setSuccess('Last price change undone.');
      fetchPriceHistory();
    } catch (err) {
      setError(err.response?.data?.error || 'An error occurred');
    }
    setUndoLoading(false);
  };

  return (
    <Box sx={{ width: '100%', mt: 4, display: 'flex' }}>
      <Paper sx={{ p: 4, width: '100%', maxWidth: 900, minHeight: 600, boxShadow: 3, background: '#fafbfc' }}>
        <Typography variant="h4" gutterBottom sx={{ fontWeight: 700, mb: 3 }}>Price Management</Typography>
        <Typography variant="body1" sx={{ mb: 2, color: 'text.secondary' }}>
          {productCount !== null ? `${productCount} products will be updated.` : 'Loading product count...'}
        </Typography>
        <Grid container spacing={2} sx={{ mb: 2 }}>
          <Grid item xs={12} sm={6}>
            <form onSubmit={handlePercentSubmit} style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <TextField
                label="Percentage (%)"
                type="number"
                value={percent}
                onChange={e => setPercent(e.target.value)}
                required
                size="small"
                sx={{ width: 140 }}
                inputProps={{ step: 'any' }}
                InputLabelProps={{ shrink: true }}
              />
              <Button type="submit" variant="contained" disabled={loading} sx={{ minWidth: 90 }}>
                {loading ? <CircularProgress size={18} /> : 'Apply %'}
              </Button>
            </form>
          </Grid>
          <Grid item xs={12} sm={6}>
            <form onSubmit={handleDiscountSubmit} style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <TextField
                label="Discount ($)"
                type="number"
                value={discount}
                onChange={e => setDiscount(e.target.value)}
                required
                size="small"
                sx={{ width: 140 }}
                inputProps={{ step: 'any' }}
                InputLabelProps={{ shrink: true }}
              />
              <Button type="submit" variant="contained" disabled={discountLoading} sx={{ minWidth: 90 }}>
                {discountLoading ? <CircularProgress size={18} /> : 'Apply $'}
              </Button>
            </form>
          </Grid>
          <Grid item xs={12} sm={6}>
            <Button fullWidth variant="outlined" color="secondary" onClick={handleReset} disabled={resetLoading} sx={{ fontWeight: 600, height: 40 }}>
              {resetLoading ? <CircularProgress size={18} /> : 'Reset All Prices'}
            </Button>
          </Grid>
          <Grid item xs={12} sm={6}>
            <Button fullWidth variant="outlined" color="warning" onClick={handleUndo} disabled={undoLoading} sx={{ fontWeight: 600, height: 40 }}>
              {undoLoading ? <CircularProgress size={18} /> : 'Undo Last Change'}
            </Button>
          </Grid>
        </Grid>
        {success && <Alert severity="success" sx={{ mb: 2 }}>{success}</Alert>}
        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
        <Typography variant="body2" color="text.secondary" sx={{ mb: 3, lineHeight: 1.7 }}>
          <b>Bulk price management:</b> Enter a positive value to increase prices, or a negative value to decrease prices. For example, 10 increases all prices by 10%, -5 decreases all prices by 5%.<br/>
          Or apply a fixed discount to all products. You can also reset all prices to original sample values, or undo the last price change.
        </Typography>
        <Divider sx={{ my: 3 }} />
        <Grid container spacing={2}>
          <Grid item xs={12} sm={6}>
            <Typography variant="h6" gutterBottom sx={{ fontWeight: 600 }}>Price Range Stats</Typography>
            <List dense sx={{ mb: 2 }}>
              {rangeStats.map(r => (
                <ListItem key={r.label} sx={{ pl: 0 }}><ListItemText primary={<span style={{ fontWeight: 500 }}>{r.label}:</span>} secondary={`${r.count} products`} /></ListItem>
              ))}
            </List>
          </Grid>
          <Grid item xs={12} sm={6}>
            <Typography variant="h6" gutterBottom sx={{ fontWeight: 600 }}>Recent Price Changes</Typography>
            <List dense>
              {priceHistory.length === 0 && <ListItem sx={{ pl: 0 }}><ListItemText primary="No recent price changes." /></ListItem>}
              {priceHistory.map((h, i) => (
                <ListItem key={i} sx={{ pl: 0 }}>
                  <ListItemText primary={<span style={{ fontWeight: 500 }}>{h.name}</span>} secondary={`$${h.old} → $${h.new} (${new Date(h.ts).toLocaleString()})`} />
                </ListItem>
              ))}
            </List>
          </Grid>
          <Grid item xs={12} sm={6}>
            <Typography variant="h6" gutterBottom sx={{ fontWeight: 600 }}>Top 5 Most Expensive</Typography>
            <List dense>
              {topExpensive.map(p => (
                <ListItem key={p.id} sx={{ pl: 0 }}><ListItemText primary={<span style={{ fontWeight: 500 }}>{p.name}</span>} secondary={`$${p.price}`} /></ListItem>
              ))}
            </List>
          </Grid>
          <Grid item xs={12} sm={6}>
            <Typography variant="h6" gutterBottom sx={{ fontWeight: 600 }}>Top 5 Cheapest</Typography>
            <List dense>
              {topCheap.map(p => (
                <ListItem key={p.id} sx={{ pl: 0 }}><ListItemText primary={<span style={{ fontWeight: 500 }}>{p.name}</span>} secondary={`$${p.price}`} /></ListItem>
              ))}
            </List>
          </Grid>
        </Grid>
      </Paper>
    </Box>
  );
}

export default PriceManagement; 