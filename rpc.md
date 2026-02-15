assign_rider_to_delivery:

DECLARE
  v_rider_profile RECORD;
  v_order RECORD;
BEGIN
  -- 1. Find order by tx_ref and validate status
  SELECT * INTO v_order
  FROM delivery_orders
  WHERE tx_ref = p_tx_ref;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'Order not found for tx_ref: %', p_tx_ref;
  END IF;

  -- Check if payment is completed
  IF v_order.payment_status != 'PAID' THEN
    RAISE EXCEPTION 'Order payment not completed. Payment status: %', v_order.payment_status;
  END IF;

  -- Check if order already has a rider
  IF v_order.rider_id IS NOT NULL THEN
    RAISE EXCEPTION 'Order already assigned to rider %', v_order.rider_id;
  END IF;

  -- Check if order is in correct status
  IF v_order.delivery_status NOT IN ('PAID_NEEDS_RIDER', 'PENDING') THEN
    RAISE EXCEPTION 'Order status is % - cannot assign rider', v_order.delivery_status;
  END IF;

  -- 2. Validate rider and get their profile details
  SELECT 
    p.id,
    p.full_name,
    p.phone_number,
    p.email,
    p.dispatcher_id,
    p.is_online,
    p.has_delivery,
    p.is_blocked,
    p.user_type
  INTO v_rider_profile
  FROM profiles p
  WHERE p.id = p_rider_id
    AND p.user_type = 'RIDER'
    AND p.is_online = true
    AND p.has_delivery = false
    AND p.is_blocked = false;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'Rider not available. Either not found, offline, blocked, or not a dispatch rider';
  END IF;

  -- 3. Assign rider to order and update profile
  UPDATE delivery_orders
  SET 
    rider_id = p_rider_id,
    dispatch_id = v_rider_profile.dispatcher_id,
    rider_phone_number = v_rider_profile.phone_number, -- NEW: Save phone number
    delivery_status = 'ASSIGNED',
    updated_at = NOW()
  WHERE tx_ref = p_tx_ref;

  -- NEW: Set rider status to busy
  UPDATE profiles
  SET has_delivery = true
  WHERE id = p_rider_id;

  -- 4. Return success with full details
  RETURN jsonb_build_object(
    'success', true,
    'message', 'Rider assigned successfully',
    'tx_ref', p_tx_ref,
    'order_id', v_order.id,
    'rider_id', p_rider_id,
    'dispatch_id', v_rider_profile.dispatcher_id,
    'rider_name', v_rider_profile.full_name,
    'has_delivery', true,
    'rider_phone', v_rider_profile.phone_number,
    'rider_email', v_rider_profile.email,
    'order_status', 'ASSIGNED'
  );

EXCEPTION
  WHEN OTHERS THEN
    RAISE EXCEPTION 'Failed to assign rider: %', SQLERRM;
END;

accept_delivery
DECLARE
  v_order RECORD;
BEGIN
  -- 1. Find and validate order
  SELECT * INTO v_order
  FROM delivery_orders
  WHERE tx_ref = p_tx_ref;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'Order not found for tx_ref: %', p_tx_ref;
  END IF;

  -- Allow acceptance if:
  -- 1. Status is PAID_NEEDS_RIDER (Rider accepts open order)
  -- 2. Status is ASSIGNED and assigned to this rider (Rider confirms assignment)
  IF v_order.delivery_status NOT IN ('PAID_NEEDS_RIDER', 'ASSIGNED') THEN
    RAISE EXCEPTION 'Order status is % - cannot accept', v_order.delivery_status;
  END IF;

  -- If already assigned, must be matched to this rider
  IF v_order.delivery_status = 'ASSIGNED' AND v_order.rider_id != p_rider_id THEN
    RAISE EXCEPTION 'This order is already assigned to another rider';
  END IF;

  -- 2. Update status to ASSIGNED (Accepted = Assigned in this flow)
  UPDATE delivery_orders
  SET 
    delivery_status = 'ACCEPTED',
    rider_id = p_rider_id, -- Ensure rider is set
    updated_at = NOW()
  WHERE tx_ref = p_tx_ref;

  RETURN jsonb_build_object(
    'success', true,
    'message', 'Delivery accepted successfully',
    'tx_ref', p_tx_ref,
    'delivery_status', 'ACCEPTED'
  );

EXCEPTION
  WHEN OTHERS THEN
    RAISE EXCEPTION 'Failed to accept delivery: %', SQLERRM;
END;

decline_delivery

DECLARE
    v_transaction RECORD;
    v_delivery_id UUID;
    v_sender_id UUID;
    v_delivery_fee NUMERIC;
BEGIN
    -- Find transaction by tx_ref
    SELECT * INTO v_transaction
    FROM transactions
    WHERE tx_ref = p_tx_ref
    AND transaction_type = 'ESCROW_HOLD';
    
    IF v_transaction IS NOT NULL THEN
        v_delivery_id := v_transaction.order_id;
        v_sender_id := v_transaction.from_user_id;
        v_delivery_fee := v_transaction.amount;
        
        -- Refund sender
        PERFORM update_user_wallet(
            v_sender_id,
            v_delivery_fee::TEXT,
            '-' || v_delivery_fee::TEXT
        );
        
        -- Create refund transaction
        INSERT INTO transactions (
            amount, from_user_id, to_user_id, order_id, wallet_id,
            transaction_type, payment_status, order_type, details
        ) VALUES (
            v_delivery_fee, v_sender_id, v_sender_id, v_delivery_id, v_sender_id,
            'REFUNDED', 'SUCCESS', 'DELIVERY',
            jsonb_build_object(
                'label', 'CREDIT',
                'reason', 'DELIVERY_DECLINED',
                'declined_by', 'RIDER'
            )
        );
    END IF;
    
    -- Clear rider_id from delivery
    UPDATE delivery_orders
    SET rider_id = NULL,
        dispatch_id = NUll,
        updated_at = NOW()
    WHERE id = v_delivery_id;
    
END;


pickup_delivery

DECLARE
  v_order RECORD;
BEGIN
  -- 1. Find and validate order
  SELECT * INTO v_order
  FROM delivery_orders
  WHERE tx_ref = p_tx_ref;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'Order not found for tx_ref: %', p_tx_ref;
  END IF;

  IF v_order.delivery_status != 'ACCEPTED' THEN
    RAISE EXCEPTION 'Order must be ACCEPTED before pickup. Current status: %', v_order.delivery_status;
  END IF;

  IF v_order.rider_id != p_rider_id THEN
    RAISE EXCEPTION 'This order is not assigned to you';
  END IF;

  -- 2. Update status to PICKED_UP
  UPDATE delivery_orders
  SET 
    delivery_status = 'PICKED_UP',
    updated_at = NOW()
  WHERE tx_ref = p_tx_ref;

  -- 3. Update Dispatcher Escrow Balance
  -- Move the delivery fee to the dispatcher's escrow balance
  PERFORM public.update_user_wallet(
    v_order.dispatch_id, 
    0, -- balance_change
    v_order.delivery_fee -- escrow_balance_change
  );

  RETURN jsonb_build_object(
    'success', true,
    'message', 'Delivery marked as picked up. Escrow balance updated.',
    'tx_ref', p_tx_ref,
    'delivery_status', 'PICKED_UP'
  );

EXCEPTION
  WHEN OTHERS THEN
    RAISE EXCEPTION 'Failed to mark pickup: %', SQLERRM;
END;

mark_delivery_delivered

BEGIN
  -- 1. Validate status and rider
  IF NOT EXISTS (
    SELECT 1 FROM delivery_orders 
    WHERE tx_ref = p_tx_ref AND rider_id = p_rider_id AND delivery_status = 'PICKED_UP'
  ) THEN
    RAISE EXCEPTION 'Order not found, not assigned to you, or not in PICKED_UP status';
  END IF;

  -- 2. Update status
  UPDATE delivery_orders
  SET 
    delivery_status = 'DELIVERED',
    updated_at = NOW()
  WHERE tx_ref = p_tx_ref;

  RETURN jsonb_build_object(
    'success', true,
    'message', 'Delivery marked as delivered',
    'tx_ref', p_tx_ref,
    'delivery_status', 'DELIVERED'
  );
END;

mark_delivery_completed

DECLARE
  v_order RECORD;
BEGIN
  -- 1. Validate status and sender
  SELECT * INTO v_order
  FROM delivery_orders
  WHERE tx_ref = p_tx_ref AND sender_id = p_sender_id;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'Order not found or you are not the sender';
  END IF;

  IF v_order.delivery_status != 'DELIVERED' THEN
    RAISE EXCEPTION 'Order must be DELIVERED before it can be marked COMPLETED';
  END IF;

  -- 2. Update order status
  UPDATE delivery_orders
  SET 
    delivery_status = 'COMPLETED',
    updated_at = NOW()
  WHERE tx_ref = p_tx_ref;

  -- 3. Update Dispatch Wallet
  PERFORM public.update_user_wallet(
    v_order.dispatch_id,
    v_order.amount_due_dispatch, -- balance_change (payout)
    -v_order.delivery_fee         -- escrow_balance_change (release)
  );

  -- 4. Update Sender Wallet
  PERFORM public.update_user_wallet(
    v_order.sender_id,
    0,                     -- balance_change
    -v_order.delivery_fee   -- escrow_balance_change (release)
  );

  RETURN jsonb_build_object(
    'success', true,
    'message', 'Delivery completed and funds released.',
    'tx_ref', p_tx_ref,
    'delivery_status', 'COMPLETED'
  );

EXCEPTION
  WHEN OTHERS THEN
    RAISE EXCEPTION 'Failed to complete delivery: %', SQLERRM;
END;

cancel_delivery_by_rider

DECLARE
    v_delivery RECORD;
BEGIN
    -- Fetch delivery to get rider_id
    SELECT * INTO v_delivery
    FROM delivery_orders
    WHERE id = p_order_id;
    
    IF v_delivery IS NOT NULL AND v_delivery.rider_id IS NOT NULL THEN
        -- Increment rider cancel count
        UPDATE profiles
        SET order_cancel_count = COALESCE(order_cancel_count, 0) + 1
        WHERE id = v_delivery.rider_id;
    END IF;
END;

cancel_delivery_by_sender

DECLARE
  v_sender_id UUID;
  v_delivery_status TEXT;
  v_rider_id UUID;
  v_total_price NUMERIC;
BEGIN
  -- Fetch order details
  SELECT sender_id, delivery_status, rider_id, total_price
  INTO v_sender_id, v_delivery_status, v_rider_id, v_total_price
  FROM delivery_orders
  WHERE id = p_order_id;
  -- Validation
  IF v_sender_id != auth.uid() THEN
    RAISE EXCEPTION 'Not authorized';
  END IF;
  IF v_delivery_status IN ('DELIVERED', 'COMPLETED', 'CANCELLED') THEN
    RAISE EXCEPTION 'Cannot cancel order in current status: %', v_delivery_status;
  END IF;
  -- Logic based on status
  IF v_delivery_status = 'PICKED_UP' THEN
    -- Mark for return
    UPDATE delivery_orders
    SET 
      is_sender_cancelled = true,
      cancel_reason = p_reason
    WHERE id = p_order_id;
    
    RETURN jsonb_build_object('success', true, 'message', 'Order marked for return');
    
  ELSE
    -- Initial Cancellation (PENDING, ASSIGNED, ACCEPTED)
    -- Update Order
    UPDATE delivery_orders
    SET 
      delivery_status = 'CANCELLED',
      rider_id = NULL,
      dispatch_id = NULL,
      rider_phone_number = NULL,
      p_reason = p_reason
    WHERE id = p_order_id;
    -- Update Rider Profile if assigned
    IF v_rider_id IS NOT NULL THEN
      UPDATE profiles
      SET has_delivery = false
      WHERE id = v_rider_id;
    END IF;
    -- Refund Sender Wallet (assuming 'balance' is the main wallet balance)
    UPDATE wallets
    SET balance = balance + v_total_price
    WHERE user_id = v_sender_id;
    RETURN jsonb_build_object('success', true, 'message', 'Order cancelled and refunded');
  END IF;
END;
