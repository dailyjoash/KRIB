
import React, { useContext } from 'react'
import { Link } from 'react-router-dom'
import { AuthContext } from '../context/AuthContext'

export default function NavBar(){
  const { user, logout } = useContext(AuthContext)
  return (
    <nav style={{display:'flex', justifyContent:'space-between', alignItems:'center', padding:'8px 16px', background:'#111', color:'#fff'}}>
      <div><Link to='/dashboard' style={{color:'#fff', textDecoration:'none'}}>KRIB</Link></div>
      <div>
        {user && user.role === 'landlord' && <Link to='/properties/new' style={{color:'#fff', marginRight:12}}>Add Property</Link>}
        {user && <Link to='/maintenance/new' style={{color:'#fff', marginRight:12}}>Report Issue</Link>}
        {user ? <button onClick={logout}>Logout</button> : <Link to='/'>Login</Link>}
      </div>
    </nav>
  )
}
