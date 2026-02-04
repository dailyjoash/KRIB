
import React, { useState } from 'react'
import api from '../services/api'
import { useNavigate } from 'react-router-dom'

export default function PropertiesNew(){
  const [title, setTitle] = useState('')
  const [address, setAddress] = useState('')
  const [description, setDescription] = useState('')
  const nav = useNavigate()

  const submit = async (e) => {
    e.preventDefault()
    try {
      await api.post('/api/properties/', {title, address, description})
      nav('/dashboard')
    } catch (err) {
      alert('Failed to create property')
    }
  }

  return (
    <div className='card'>
      <h3>Add Property</h3>
      <form onSubmit={submit}>
        <input placeholder='Title' value={title} onChange={e=>setTitle(e.target.value)} />
        <input placeholder='Address' value={address} onChange={e=>setAddress(e.target.value)} />
        <textarea placeholder='Description' value={description} onChange={e=>setDescription(e.target.value)} />
        <button type='submit'>Create</button>
      </form>
    </div>
  )
}
