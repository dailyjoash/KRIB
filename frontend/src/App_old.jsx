
import React from 'react'
import { Outlet } from 'react-router-dom'

import NavBar from './components/NavBar'
import PropertiesNew from './components/PropertiesNew'
import LeasesNew from './components/LeasesNew'
import MaintenanceNew from './components/MaintenanceNew'
import ProtectedRoute from './components/ProtectedRoute'

export default function App(){
  return (
    <div className='app'>
      <header><h1>KRIB</h1></header>
      <NavBar />
      <main><Outlet /></main>
    </div>
  )
}
