
import React, { useState } from 'react'
import api from '../services/api'
import { useNavigate } from 'react-router-dom'

export default function MaintenanceNew(){
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [leaseId, setLeaseId] = useState('')
  const nav = useNavigate()

  const submit = async (e) => {
    e.preventDefault()
    try {
      await api.post('/maintenance/', {title, description, lease: leaseId})
      nav('/dashboard')
    } catch (err) {
      alert('Failed to create maintenance request')
    }
  }

  return (
    <div className='card'>
      <h3>Report Maintenance</h3>
      <form onSubmit={submit}>
        <input placeholder='Title' value={title} onChange={e=>setTitle(e.target.value)} />
        <textarea placeholder='Description' value={description} onChange={e=>setDescription(e.target.value)} />
        <input placeholder='Lease ID' value={leaseId} onChange={e=>setLeaseId(e.target.value)} />
        <button type='submit'>Report</button>
      </form>
    </div>
  )
}
