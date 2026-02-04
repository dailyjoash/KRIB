
import React, { useState } from 'react'
import api from '../services/api'
import { useNavigate } from 'react-router-dom'

export default function MaintenanceNew(){
  const [propertyId, setPropertyId] = useState('')
  const [issue, setIssue] = useState('')
  const nav = useNavigate()

  const submit = async (e) => {
    e.preventDefault()
    try {
      await api.post('/api/maintenance/', {property: propertyId, issue})
      nav('/dashboard')
    } catch (err) {
      alert('Failed to create maintenance request')
    }
  }

  return (
    <div className='card'>
      <h3>Report Maintenance</h3>
      <form onSubmit={submit}>
        <input placeholder='Property ID' value={propertyId} onChange={e=>setPropertyId(e.target.value)} />
        <textarea placeholder='Issue description' value={issue} onChange={e=>setIssue(e.target.value)} />
        <button type='submit'>Report</button>
      </form>
    </div>
  )
}
