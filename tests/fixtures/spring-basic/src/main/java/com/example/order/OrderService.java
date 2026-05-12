package com.example.order;

import org.springframework.stereotype.Service;

@Service
public class OrderService {
    public OrderResponse create(CreateOrderRequest request) {
        if (request.getQuantity() < 1) {
            throw new IllegalArgumentException("quantity must be positive");
        }
        return new OrderResponse();
    }

    public OrderResponse get(Long orderId) {
        return new OrderResponse();
    }
}
