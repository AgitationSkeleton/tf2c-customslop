// CustomSlop server-side attribute effects (research prototype - NOT deployed).
// Pattern copied from the April Fools pack (mod_shoot_self.nut): the schema declares the
// attribute, VScript reads it from the active weapon on player_shoot.
// Include from mapspawn.nut next to the April Fools include:
//   if ( IsServer() ) ::DoIncludeScript( "/customslop/sv_customslop", this );

::ListenToGameEvent( "player_shoot", function( hEvent )
{
	local hPlayer = GetPlayerFromUserID( hEvent.userid );
	if ( !hPlayer )
		return;

	local hWeapon = hPlayer.GetActiveWeapon();
	if ( !hWeapon )
		return;

	// "customslop ignite self on attack" (25900): seconds of afterburn on the wielder
	local flSelf = hWeapon.GetAttribute( "customslop ignite self on attack", 0 );
	if ( flSelf > 0 )
		hPlayer.IgnitePlayerEx( flSelf );
}, "customslop_ignite_self" );

Msg( "CustomSlop scripts initialized.\n" );
