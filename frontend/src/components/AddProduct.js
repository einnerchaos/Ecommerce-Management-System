import React, { useState, useEffect } from 'react';
import {
  Box, Paper, Typography, TextField, Button, MenuItem, Stack, Grid, IconButton, ImageList, ImageListItem
} from '@mui/material';
import AddPhotoAlternateIcon from '@mui/icons-material/AddPhotoAlternate';
import DeleteIcon from '@mui/icons-material/Delete';
import axios from 'axios';

function AddProduct() {
  const [form, setForm] = useState({
    name: '',
    description: '',
    price: '',
    stock: '',
    category_id: '',
  });
  const [categories, setCategories] = useState([]);
  const [images, setImages] = useState([]); // {file, url}
  const [submitting, setSubmitting] = useState(false);
  const [success, setSuccess] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    axios.get('/api/categories').then(res => setCategories(res.data));
  }, []);

  const handleInput = e => {
    setForm({ ...form, [e.target.name]: e.target.value });
  };

  const handleImageChange = e => {
    const files = Array.from(e.target.files);
    const newImages = files.map(file => ({ file, url: URL.createObjectURL(file) }));
    setImages(prev => [...prev, ...newImages]);
  };

  const handleImageRemove = idx => {
    setImages(prev => prev.filter((_, i) => i !== idx));
  };

  const handleSubmit = async e => {
    e.preventDefault();
    setSubmitting(true);
    setSuccess('');
    setError('');
    try {
      const data = new FormData();
      Object.entries(form).forEach(([k, v]) => data.append(k, v));
      images.forEach(img => data.append('images', img.file));
      await axios.post('/api/products', data, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      setSuccess('Product added successfully!');
      setForm({ name: '', description: '', price: '', stock: '', category_id: '' });
      setImages([]);
    } catch (err) {
      setError(err.response?.data?.error || 'An error occurred');
    }
    setSubmitting(false);
  };

  return (
    <Box sx={{ width: '100%', mt: 4 }}>
      <Paper sx={{ p: 4, width: '100%', maxWidth: 600 }}>
        <Typography variant="h4" gutterBottom>Add Product</Typography>
        <form onSubmit={handleSubmit}>
          <Stack spacing={2}>
            <TextField label="Product Name" name="name" value={form.name} onChange={handleInput} required fullWidth />
            <TextField label="Description" name="description" value={form.description} onChange={handleInput} multiline rows={3} fullWidth />
            <Grid container spacing={2}>
              <Grid item xs={6}>
                <TextField label="Price" name="price" type="number" value={form.price} onChange={handleInput} required fullWidth inputProps={{ step: 'any' }} />
              </Grid>
              <Grid item xs={6}>
                <TextField label="Stock" name="stock" type="number" value={form.stock} onChange={handleInput} required fullWidth />
              </Grid>
            </Grid>
            <TextField select label="Category" name="category_id" value={form.category_id} onChange={handleInput} required fullWidth>
              {categories.map(cat => (
                <MenuItem key={cat.id} value={cat.id}>{cat.name}</MenuItem>
              ))}
            </TextField>
            <Box>
              <Button variant="outlined" component="label" startIcon={<AddPhotoAlternateIcon />}>
                Add Images
                <input type="file" accept="image/*" multiple hidden onChange={handleImageChange} />
              </Button>
              <ImageList cols={3} rowHeight={100} sx={{ mt: 1 }}>
                {images.map((img, idx) => (
                  <ImageListItem key={idx}>
                    <img src={img.url} alt="preview" style={{ objectFit: 'cover', width: '100%', height: '100%' }} />
                    <IconButton size="small" sx={{ position: 'absolute', top: 2, right: 2, bgcolor: 'white' }} onClick={() => handleImageRemove(idx)}>
                      <DeleteIcon fontSize="small" />
                    </IconButton>
                  </ImageListItem>
                ))}
              </ImageList>
            </Box>
            <Button type="submit" variant="contained" disabled={submitting}>{submitting ? 'Adding...' : 'Add Product'}</Button>
            {success && <Typography color="success.main">{success}</Typography>}
            {error && <Typography color="error.main">{error}</Typography>}
          </Stack>
        </form>
      </Paper>
    </Box>
  );
}

export default AddProduct; 