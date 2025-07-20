import React from 'react';
import { Box, Typography, Paper, Button, Stack } from '@mui/material';
import DownloadIcon from '@mui/icons-material/Download';
import axios from 'axios';

function downloadFile(url, filename) {
  axios.get(url, { responseType: 'blob' }).then(res => {
    const url = window.URL.createObjectURL(new Blob([res.data]));
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', filename);
    document.body.appendChild(link);
    link.click();
    link.remove();
  });
}

function Reports() {
  return (
    <Box sx={{ mt: 5, ml: 0, width: '100%' }}>
      <Paper sx={{ p: 4, width: '100%', maxWidth: 600 }}>
        <Typography variant="h4" gutterBottom>Reports</Typography>
        <Typography variant="body1" sx={{ mb: 3 }}>
          Export key data as Excel reports for offline analysis or sharing.
        </Typography>
        <Stack spacing={3}>
          <Box>
            <Typography variant="h6">Products Report</Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
              Download a full list of products with stock, price, and category info.
            </Typography>
            <Button variant="contained" startIcon={<DownloadIcon />} onClick={() => downloadFile('/api/reports/products', 'products_report.xlsx')}>
              Download Products Excel
            </Button>
          </Box>
          <Box>
            <Typography variant="h6">Orders Report</Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
              Download all orders with user, total, status, and item details.
            </Typography>
            <Button variant="contained" startIcon={<DownloadIcon />} onClick={() => downloadFile('/api/reports/orders', 'orders_report.xlsx')}>
              Download Orders Excel
            </Button>
          </Box>
        </Stack>
      </Paper>
    </Box>
  );
}

export default Reports; 