
import React, { useState, useEffect } from 'react'
import api from '../services/api'
import { useNavigate } from 'react-router-dom'

export default function LeasesNew(){
  const [properties, setProperties] = useState([])
  const [tenantId, setTenantId] = useState('')
  const [propertyId, setPropertyId] = useState('')
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [rentAmount, setRentAmount] = useState('')
  const [agreement, setAgreement] = useState(null)
  const nav = useNavigate()

  useEffect(()=>{
    async function load(){
      const res = await api.get('/properties/')
      setProperties(res.data)
    }
    load()
  },[])

  const submit = async (e) => {
    e.preventDefault()
    try {
      const form = new FormData()
      form.append('property', propertyId)
      form.append('tenant', tenantId)
      form.append('start_date', startDate)
      form.append('end_date', endDate)
      form.append('rent_amount', rentAmount)
      if(agreement) form.append('agreement', agreement)
      await api.post('/leases/', form, { headers: {'Content-Type': 'multipart/form-data'} })
      nav('/dashboard')
    } catch (err) {
      console.error(err)
      alert('Failed to create lease')
    }
  }

  return (
    <div className='card'>
      <h3>Create Lease</h3>
      <form onSubmit={submit}>
        <select onChange={e=>setPropertyId(e.target.value)} value={propertyId}>
          <option value=''>Select property</option>
          {properties.map(p=> <option key={p.id} value={p.id}>{p.title}</option>)}
        </select>
        <input placeholder='Tenant (ID)' value={tenantId} onChange={e=>setTenantId(e.target.value)} />
        <input type='date' value={startDate} onChange={e=>setStartDate(e.target.value)} />
        <input type='date' value={endDate} onChange={e=>setEndDate(e.target.value)} />
        <input placeholder='Rent amount' value={rentAmount} onChange={e=>setRentAmount(e.target.value)} />
        <input type='file' onChange={e=>setAgreement(e.target.files[0])} />
        <button type='submit'>Create Lease</button>
      </form>
    </div>
  )
}
